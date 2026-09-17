import { useState, useMemo } from 'react'
import { api, groupByOrder } from '../api'
import type { FetchResult, ExportResult, OrderGroup, RunRecord, RunFlag } from '../api'
import {
  RefreshCw, Play, Zap, AlertTriangle, CheckCircle, Loader2,
  ChevronDown, ChevronRight, Package, ShieldAlert, Info, Search,
} from 'lucide-react'

type Stage = 'idle' | 'fetching' | 'running' | 'done' | 'error'
type Filter = 'all' | 'ready' | 'attention'

function Badge({ tone = 'neutral', children }: {
  tone?: 'neutral' | 'amber' | 'red' | 'green' | 'blue'
  children: React.ReactNode
}) {
  const tones = {
    neutral: 'bg-zinc-800 text-zinc-300 ring-zinc-700',
    amber:   'bg-amber-500/10 text-amber-300 ring-amber-500/30',
    red:     'bg-red-500/10 text-red-300 ring-red-500/30',
    green:   'bg-emerald-500/10 text-emerald-300 ring-emerald-500/30',
    blue:    'bg-sky-500/10 text-sky-300 ring-sky-500/30',
  }
  return (
    <span className={`px-2 py-0.5 rounded-md text-[11px] font-medium ring-1 ring-inset whitespace-nowrap ${tones[tone]}`}>
      {children}
    </span>
  )
}

/** Arabic needs its own font + RTL direction or it renders as tofu boxes. */
function Arabic({ children }: { children: string }) {
  return <span dir="rtl" className="arabic text-zinc-400">{children}</span>
}

function ProgressBar({ stage, current, total }: { stage: string; current: number; total: number }) {
  const pct = total > 0 ? Math.round((current / total) * 100) : 0
  return (
    <div className="flex flex-col gap-2">
      <div className="flex justify-between text-xs">
        <span className="capitalize font-semibold text-zinc-200">{stage || 'starting'}</span>
        <span className="text-zinc-500 font-mono">{total > 0 ? `${current}/${total}` : '…'}</span>
      </div>
      <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
        <div className="h-full bg-gradient-to-r from-amber-500 to-amber-400 rounded-full transition-all duration-300"
             style={{ width: `${pct || 6}%` }} />
      </div>
    </div>
  )
}

function FlagRow({ kind, detail, severity }: { kind: string; detail: string; severity: string }) {
  const Icon = severity === 'critical' ? ShieldAlert
             : severity === 'informational' ? Info : AlertTriangle
  const colour = severity === 'critical' ? 'text-red-400'
               : severity === 'informational' ? 'text-sky-400' : 'text-amber-400'
  return (
    <div className="flex items-start gap-2 text-xs py-1.5">
      <Icon size={13} className={`${colour} mt-0.5 shrink-0`} />
      <div className="min-w-0">
        <span className={`font-semibold ${colour}`}>{kind}</span>
        <span className="text-zinc-500"> — </span>
        <span className="text-zinc-400 break-words">{detail}</span>
      </div>
    </div>
  )
}

function RecordBlock({ rec }: { rec: RunRecord }) {
  const flags: RunFlag[] = rec.flags ?? []
  return (
    <div className="rounded-lg bg-zinc-900/60 ring-1 ring-zinc-800 p-3">
      <div className="flex items-baseline gap-2 flex-wrap mb-2">
        <span className="font-medium text-zinc-100 text-sm">
          {rec.student_name || <span className="text-zinc-500 italic">no name</span>}
        </span>
        {rec.student_name_arabic && <Arabic>{rec.student_name_arabic}</Arabic>}
        {rec.blocked && <Badge tone="red">blocked</Badge>}
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-zinc-500 mb-2">
        {rec.grade  && <span>Class: <span className="text-zinc-400">{rec.grade}</span></span>}
        {rec.school && <span>School: <span className="text-zinc-400">{rec.school}</span></span>}
        <span className="font-mono text-zinc-600">{rec.template_name}</span>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {rec.items.map((it, i) => (
          <span key={i}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-zinc-800/80 text-[11px] text-zinc-300">
            {it.region_id}
            {it.qty > 1 && <span className="text-amber-400 font-semibold">×{it.qty}</span>}
          </span>
        ))}
      </div>

      {flags.length > 0 && (
        <div className="mt-2 pt-2 border-t border-zinc-800">
          {flags.map((f, i) => <FlagRow key={i} kind={f.kind} detail={f.detail} severity={f.severity} />)}
        </div>
      )}
    </div>
  )
}

function OrderCard({ group, defaultOpen }: { group: OrderGroup; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  const issues = group.warnings.length + group.reviewCount
  const students = group.records.length

  const accent = group.hasBlocking ? 'border-l-red-500'
               : issues > 0        ? 'border-l-amber-500'
               :                     'border-l-emerald-500'

  return (
    <div className={`bg-zinc-900 rounded-xl ring-1 ring-zinc-800 border-l-2 ${accent} overflow-hidden animate-fade-up`}>
      <button onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-zinc-800/40 transition-colors">
        <div className="flex items-center gap-3 min-w-0">
          {open ? <ChevronDown size={15} className="text-zinc-500 shrink-0" />
                : <ChevronRight size={15} className="text-zinc-500 shrink-0" />}
          <span className="font-semibold text-zinc-100 font-mono text-sm">{group.order_number}</span>
          {group.themes.length > 0 && (
            <span className="text-zinc-400 text-xs truncate">
              {group.themes.join(' · ')}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {students > 1 && <Badge tone="blue">{students} students</Badge>}
          <Badge><Package size={10} className="inline mr-1" />{group.itemCount}</Badge>
          {group.hasBlocking
            ? <Badge tone="red">blocked</Badge>
            : issues > 0
              ? <Badge tone="amber">{issues} to review</Badge>
              : <Badge tone="green">ready</Badge>}
        </div>
      </button>

      {open && (
        <div className="px-4 pb-4 flex flex-col gap-2.5 border-t border-zinc-800 pt-3">
          {group.records.map((r, i) => <RecordBlock key={i} rec={r} />)}

          {group.warnings.length > 0 && (
            <div className="rounded-lg bg-amber-500/5 ring-1 ring-amber-500/20 px-3 py-2">
              <div className="text-[11px] font-semibold text-amber-400 uppercase tracking-wider mb-1">
                Skipped in this order
              </div>
              {group.warnings.map((w, i) => (
                <FlagRow key={i} kind={w.kind} detail={w.detail} severity="warning" />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function ProductionTab() {
  const [stage, setStage]               = useState<Stage>('idle')
  const [fetchResult, setFetchResult]   = useState<FetchResult | null>(null)
  const [exportResult, setExportResult] = useState<ExportResult | null>(null)
  const [progress, setProgress]         = useState({ stage: '', current: 0, total: 0 })
  const [error, setError]               = useState<string | null>(null)
  const [filter, setFilter]             = useState<Filter>('all')
  const [query, setQuery]               = useState('')

  const groups = useMemo(
    () => (fetchResult ? groupByOrder(fetchResult) : []),
    [fetchResult],
  )

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    return groups.filter(g => {
      const issues = g.warnings.length + g.reviewCount
      if (filter === 'ready'     && (issues > 0 || g.hasBlocking)) return false
      if (filter === 'attention' && issues === 0 && !g.hasBlocking) return false
      if (!q) return true
      return g.order_number.toLowerCase().includes(q)
        || g.themes.some(t => t.toLowerCase().includes(q))
        || g.records.some(r =>
             r.student_name.toLowerCase().includes(q) ||
             r.student_name_arabic.includes(query.trim()))
    })
  }, [groups, filter, query])

  const stats = useMemo(() => ({
    total:     groups.length,
    ready:     groups.filter(g => !g.hasBlocking && g.warnings.length + g.reviewCount === 0).length,
    attention: groups.filter(g =>  g.hasBlocking || g.warnings.length + g.reviewCount > 0).length,
    tiles:     groups.reduce((n, g) => n + g.itemCount, 0),
  }), [groups])

  const handleFetch = async () => {
    setStage('fetching'); setFetchResult(null); setExportResult(null); setError(null)
    try {
      setFetchResult(await api.fetchOrders())
      setStage('idle')
    } catch (e: unknown) {
      setError(String(e)); setStage('error')
    }
  }

  const handleExport = (force: boolean) => {
    if (!fetchResult) return
    setStage('running'); setExportResult(null); setError(null)
    api.runPipeline(force,
      p => setProgress(p),
      d => { setExportResult(d); setStage('done') },
      e => { setError(e.message); setStage('error') })
  }

  const busy = stage === 'fetching' || stage === 'running'

  return (
    <div className="flex flex-col gap-5 max-w-4xl mx-auto w-full">

      <div className="flex items-center gap-2.5 flex-wrap">
        <button onClick={handleFetch} disabled={busy}
          className="flex items-center gap-2 px-4 py-2.5 bg-zinc-800 hover:bg-zinc-700 ring-1 ring-zinc-700
                     text-sm font-medium rounded-lg transition-colors disabled:opacity-40">
          {stage === 'fetching' ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          Fetch Orders
        </button>
        {fetchResult && <>
          <button onClick={() => handleExport(false)} disabled={busy}
            className="flex items-center gap-2 px-4 py-2.5 bg-amber-500 hover:bg-amber-400
                       text-zinc-900 text-sm font-semibold rounded-lg transition-colors disabled:opacity-40">
            <Play size={14} />Export Ready Sheets
          </button>
          <button onClick={() => handleExport(true)} disabled={busy}
            className="flex items-center gap-2 px-4 py-2.5 bg-zinc-800 hover:bg-zinc-700 ring-1 ring-zinc-700
                       text-sm rounded-lg transition-colors disabled:opacity-40">
            <Zap size={14} />Force Export All
          </button>
        </>}
      </div>

      {stage === 'running' && (
        <div className="bg-zinc-900 ring-1 ring-zinc-800 rounded-xl p-4">
          <ProgressBar stage={progress.stage} current={progress.current} total={progress.total} />
        </div>
      )}

      {error && (
        <div className="bg-red-500/5 ring-1 ring-red-500/30 rounded-xl p-4 flex items-start gap-3 animate-fade-up">
          <AlertTriangle size={16} className="text-red-400 mt-0.5 shrink-0" />
          <div className="min-w-0">
            <div className="text-sm font-semibold text-red-300 mb-1">Error</div>
            <div className="text-xs text-red-400/90 font-mono break-words whitespace-pre-wrap">{error}</div>
          </div>
        </div>
      )}

      {exportResult && (
        <div className="bg-emerald-500/5 ring-1 ring-emerald-500/30 rounded-xl p-4 flex flex-col gap-2 animate-fade-up">
          <div className="flex items-center gap-2 text-emerald-400 font-semibold text-sm">
            <CheckCircle size={15} />Export complete
          </div>
          <div className="text-xs text-emerald-300/90">
            Sheets: <span className="font-mono">{exportResult.exported_sheets.join(', ') || 'none'}</span>
          </div>
          {exportResult.held_back.length > 0 &&
            <div className="text-xs text-amber-400">Held back (under threshold): {exportResult.held_back.join(', ')}</div>}
          {exportResult.oversize.length > 0 &&
            <div className="text-xs text-red-400">Oversize: {exportResult.oversize.join(', ')}</div>}
          {(exportResult.tagged ?? []).length > 0 &&
            <div className="text-xs text-emerald-400">Tagged AI-Done in Shopify: {exportResult.tagged.length} order(s)</div>}
          {(exportResult.partially_done ?? []).length > 0 &&
            <div className="text-xs text-amber-400">Partially done → AI-Flagged: {exportResult.partially_done.join(', ')}</div>}
          {(exportResult.untagged ?? []).length > 0 &&
            <div className="text-xs text-red-400">⚠ Could not tag in Shopify: {exportResult.untagged.join(', ')} — check credentials or tag manually via tag_commands.txt</div>}
        </div>
      )}

      {fetchResult && (
        <>
          <div className="grid grid-cols-4 gap-2.5">
            {([
              ['Orders',      stats.total,     'text-zinc-100'],
              ['Ready',       stats.ready,     'text-emerald-400'],
              ['Need review', stats.attention, 'text-amber-400'],
              ['Tiles',       stats.tiles,     'text-sky-400'],
            ] as const).map(([label, value, colour]) => (
              <div key={label} className="bg-zinc-900 ring-1 ring-zinc-800 rounded-xl px-3 py-2.5">
                <div className={`text-xl font-semibold ${colour}`}>{value}</div>
                <div className="text-[11px] text-zinc-500 uppercase tracking-wider">{label}</div>
              </div>
            ))}
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <div className="flex bg-zinc-900 ring-1 ring-zinc-800 rounded-lg p-0.5">
              {(['all', 'ready', 'attention'] as Filter[]).map(f => (
                <button key={f} onClick={() => setFilter(f)}
                  className={['px-3 py-1.5 text-xs font-medium rounded-md capitalize transition-colors',
                    filter === f ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'].join(' ')}>
                  {f === 'attention' ? 'Needs review' : f}
                </button>
              ))}
            </div>
            <div className="relative flex-1 min-w-[180px]">
              <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-600" />
              <input value={query} onChange={e => setQuery(e.target.value)}
                placeholder="Search order # or theme…"
                className="w-full bg-zinc-900 ring-1 ring-zinc-800 rounded-lg pl-8 pr-3 py-2 text-xs
                           text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:ring-amber-500/50" />
            </div>
          </div>
        </>
      )}

      {fetchResult && (
        <div className="flex flex-col gap-2.5">
          {visible.length === 0
            ? <div className="text-center py-10 text-sm text-zinc-600">No orders match this filter.</div>
            : visible.map(g => (
                <OrderCard key={g.order_number} group={g}
                  defaultOpen={false} />
              ))}
        </div>
      )}

      {!fetchResult && stage !== 'fetching' && (
        <div className="text-center py-16">
          <Package size={30} className="mx-auto text-zinc-700 mb-3" />
          <div className="text-sm text-zinc-500">Fetch orders to begin.</div>
        </div>
      )}
    </div>
  )
}
