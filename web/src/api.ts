// api.ts — typed client for the FastAPI backend
// All calls go to /api/* which Vite proxies to localhost:8000 in dev,
// and FastAPI serves directly in production.

export interface Settings {
  _auth_mode?: 'oauth' | 'static' | 'none'
  _keyring_ok?: boolean
  shopify_domain: string
  shopify_api_version: string
  in_progress_tag: string
  sheet_width_mm: number
  sheet_height_mm: number
  margin_t_mm: number
  margin_b_mm: number
  margin_l_mm: number
  margin_r_mm: number
  inter_tile_gap_mm: number
  sheet_dpi: number
  fill_threshold: number
  ironon_sheet_width_mm: number
  ironon_sheet_height_mm: number
  ironon_sheet_dpi: number
  ironon_fill_threshold: number
  pack_strategy: string
  label_tiles: boolean
  output_folder: string
  report_folder: string
  _creds_configured: boolean
  _has_client_id: boolean
  _has_static_token: boolean
}

export interface TemplateInfo {
  name: string
  ready: boolean
  has_sidecar: boolean
  fingerprint_ok: boolean
  problems: string[]
  regions: { id: string; label: string; sku_match: string[] }[]
}

export interface RunFlag {
  kind: string
  severity: 'critical' | 'warning' | 'informational' | string
  detail: string
  field?: string
}

export interface RunRecord {
  order_id: string
  order_number: string
  customer_name?: string
  student_name: string
  student_name_arabic: string
  school: string
  grade: string
  telephone?: string
  template_name: string
  blocked?: boolean
  flags?: RunFlag[]
  custom_fields?: Record<string, string>
  items: { region_id: string; qty: number; sku: string }[]
}

/** One Shopify order with every record, warning and flag that belongs to it. */
export interface OrderGroup {
  order_number: string
  customer_name: string
  themes: string[]        // unique theme names across all records in this order
  records: RunRecord[]
  warnings: { kind: string; detail: string; order_number?: string }[]
  itemCount: number
  hasBlocking: boolean
  reviewCount: number
}

/** Group records + warnings by order number — the unit the operator works in. */
export function groupByOrder(res: FetchResult): OrderGroup[] {
  const map = new Map<string, OrderGroup>()

  const ensure = (num: string): OrderGroup => {
    const key = num || '(no order number)'
    let g = map.get(key)
    if (!g) {
      g = { order_number: key, customer_name: '', themes: [], records: [], warnings: [],
            itemCount: 0, hasBlocking: false, reviewCount: 0 }
      map.set(key, g)
    }
    return g
  }

  for (const r of res.records) {
    const g = ensure(r.order_number)
    g.records.push(r)
    if (!g.customer_name && r.customer_name) g.customer_name = r.customer_name
    const theme = r.custom_fields?.theme
    if (theme && !g.themes.includes(theme)) g.themes.push(theme)
    g.itemCount += r.items.reduce((n, it) => n + it.qty, 0)
    if (r.blocked) g.hasBlocking = true
    g.reviewCount += (r.flags ?? []).length
  }

  for (const w of res.warnings) {
    const g = ensure(w.order_number ?? '')
    g.warnings.push(w)
  }

  // Orders with problems float to the top — that is what needs a human.
  return [...map.values()].sort((a, b) => {
    const score = (g: OrderGroup) =>
      (g.hasBlocking ? 2 : 0) + (g.warnings.length + g.reviewCount > 0 ? 1 : 0)
    const d = score(b) - score(a)
    return d !== 0 ? d : a.order_number.localeCompare(b.order_number)
  })
}

export interface FetchResult {
  run_id: string
  order_count: number
  warnings: { kind: string; detail: string; order_number?: string }[]
  records: RunRecord[]
}

export interface ExportResult {
  run_id: string
  exported_sheets: number[]
  held_back: string[]
  oversize: string[]
  tagged: string[]
  untagged: string[]
  partially_done: string[]
}

export interface ReportSheet {
  no: string
  date: string
  fill: number
  forced: boolean
  tiles: { x: number; y: number; w: number; h: number; p: string }[]
  rows: {
    ord: string; od: string; cust: string; stu: string
    ar: string; school: string; grade: string; p: string; q: number
  }[]
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status} — ${text.slice(0, 200)}`)
  }
  return res.json()
}

export const api = {
  getSettings: ()                             => req<Settings>('GET', '/api/settings'),
  saveSettings: (s: Partial<Settings>,
                 creds?: { client_id?: string; client_secret?: string; static_token?: string }) =>
    req<{ ok: boolean }>('POST', '/api/settings', { settings: s, ...creds }),

  testConnection: () => req<{ ok: boolean; message: string }>('POST', '/api/shopify/test'),
  clearCredentials: () => req<{ ok: boolean; message: string }>('POST', '/api/shopify/clear-credentials'),
  resetSheetCount: (value: number) =>
    req<{ ok: boolean; previous: number; next_sheet: number }>(
      'POST', '/api/settings/reset-sheet-count', { value }),
  orderCount:     () => req<{ count: number }>('GET', '/api/shopify/order-count'),

  listTemplates: () => req<TemplateInfo[]>('GET', '/api/templates'),
  doctor:        () => req<Record<string, unknown>>('GET', '/api/doctor'),

  fetchOrders: () => req<FetchResult>('POST', '/api/pipeline/fetch-only'),

  listRuns: () => req<{ run_id: string; complete: boolean }[]>('GET', '/api/runs'),

  /** Production history. Served from report_data.json, which the pipeline
   *  writes on every export. Pass refresh=true to force a rebuild from the
   *  XLSX workbook (used by the Refresh button). */
  getReport: (refresh = false) => req<{
    sheets: ReportSheet[]
    products: Record<string, { label: string; colour: string }>
    skipped_rows: number
    generated?: string
    source?: 'cache' | 'rebuilt'
  }>('GET', `/api/report${refresh ? '?refresh=1' : ''}`),

  /** Subscribe to pipeline SSE stream. Returns an EventSource. */
  runPipeline: (force: boolean,
                onProgress: (d: { stage: string; current: number; total: number }) => void,
                onDone: (d: ExportResult) => void,
                onError: (d: { stage: string; message: string }) => void) => {
    const es = new EventSource(`/api/pipeline/run?force=${force}`)
    es.addEventListener('progress', e => onProgress(JSON.parse(e.data)))
    es.addEventListener('done',     e => { onDone(JSON.parse(e.data)); es.close() })
    es.addEventListener('error',    e => {
      if ((e as MessageEvent).data) onError(JSON.parse((e as MessageEvent).data))
      es.close()
    })
    return es
  },
}
