import { useState, useEffect, useRef, useCallback } from 'react'
import { api } from '../api'
import type { Settings } from '../api'
import { CheckCircle, XCircle, Loader2 } from 'lucide-react'

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-medium text-zinc-400 uppercase tracking-wider">{label}</label>
      {children}
    </div>
  )
}

function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input {...props}
      className="bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100
                 focus:outline-none focus:border-amber-500 placeholder:text-zinc-600 w-full" />
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 flex flex-col gap-4">
      <h2 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider">{title}</h2>
      {children}
    </div>
  )
}

/** Debounce: returns a stable callback that fires after `ms` ms of no calls. */
function useDebounce<T extends unknown[]>(fn: (...args: T) => void, ms: number) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  return useCallback((...args: T) => {
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => fn(...args), ms)
  }, [fn, ms])
}

export default function SettingsTab() {
  const [cfg, setCfg]           = useState<Partial<Settings>>({})
  const [clientId, setClientId]       = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [staticToken, setStaticToken] = useState('')
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [resetValue, setResetValue] = useState(0)
  const [resetMsg, setResetMsg] = useState<string | null>(null)
  const [testing, setTesting]   = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null)
  const [clearing, setClearing] = useState(false)
  const isFirstLoad = useRef(true)

  useEffect(() => {
    api.getSettings().then(s => setCfg(s)).catch(console.error)
  }, [])

  const handleResetSheetCount = async () => {
    try {
      const r = await api.resetSheetCount(resetValue)
      setResetMsg(`Done — next sheet will be #${String(r.next_sheet).padStart(3, '0')}`)
      setTimeout(() => setResetMsg(null), 4000)
    } catch {
      setResetMsg('Reset failed')
      setTimeout(() => setResetMsg(null), 3000)
    }
  }

  const doSave = useCallback(async (current: Partial<Settings>) => {
    setSaveState('saving')
    try {
      await api.saveSettings(current, {})
      setSaveState('saved')
      setTimeout(() => setSaveState('idle'), 2000)
    } catch {
      setSaveState('error')
      setTimeout(() => setSaveState('idle'), 3000)
    }
  }, [])

  const debouncedSave = useDebounce(doSave, 600)

  const set = (k: keyof Settings, v: unknown) => {
    setCfg(c => {
      const next = { ...c, [k]: v }
      if (!isFirstLoad.current) debouncedSave(next)
      return next
    })
  }

  // Don't auto-save on the initial load from API
  useEffect(() => {
    if (Object.keys(cfg).length > 0) isFirstLoad.current = false
  }, [cfg])

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const r = await api.testConnection()
      setTestResult(r)
    } finally {
      setTesting(false)
    }
  }

  const handleSaveCredentials = async () => {
    setSaveState('saving')
    try {
      await api.saveSettings(cfg, {
        client_id: clientId || undefined,
        client_secret: clientSecret || undefined,
        static_token: staticToken || undefined,
      })
      setSaveState('saved')
      setTimeout(() => setSaveState('idle'), 2000)
      setClientId(''); setClientSecret(''); setStaticToken('')
    } catch {
      setSaveState('error')
      setTimeout(() => setSaveState('idle'), 3000)
    }
  }

  const handleClearCredentials = async () => {
    setClearing(true)
    try { await api.clearCredentials() } finally { setClearing(false) }
  }

  const SaveIndicator = () => {
    if (saveState === 'saving') return (
      <span className="flex items-center gap-1.5 text-xs text-zinc-400">
        <Loader2 size={12} className="animate-spin" /> Saving…
      </span>
    )
    if (saveState === 'saved') return (
      <span className="flex items-center gap-1.5 text-xs text-green-400">
        <CheckCircle size={12} /> Saved
      </span>
    )
    if (saveState === 'error') return (
      <span className="flex items-center gap-1.5 text-xs text-red-400">
        <XCircle size={12} /> Save failed
      </span>
    )
    return null
  }

  return (
    <div className="flex flex-col gap-5 max-w-2xl">

      {/* Auto-save indicator — floats top-right */}
      <div className="flex items-center justify-between">
        <h1 className="text-sm font-semibold text-zinc-300">Settings</h1>
        <SaveIndicator />
      </div>

      {/* Shopify connection */}
      <Section title="Shopify Connection">
        <Field label="Shop domain">
          <Input placeholder="your-store.myshopify.com"
            value={cfg.shopify_domain ?? ''} onChange={e => set('shopify_domain', e.target.value)} />
        </Field>
        <Field label="API version">
          <Input placeholder="e.g. 2026-07"
            value={cfg.shopify_api_version ?? ''} onChange={e => set('shopify_api_version', e.target.value)} />
        </Field>

        <div className="border-t border-zinc-800 pt-3 flex flex-col gap-3">
          <p className="text-xs text-zinc-500">OAuth credentials (stored in OS keychain)</p>
          {cfg._keyring_ok === false && (
            <p className="text-xs text-amber-400">
              The OS keychain is unavailable, so credentials cannot be saved or read.
            </p>
          )}
          <Field label="Client ID">
            <Input placeholder={cfg._has_client_id ? '••••• saved •••••' : 'From Dev Dashboard → API credentials'}
              value={clientId} onChange={e => setClientId(e.target.value)} />
          </Field>
          <Field label="Client Secret">
            <Input type="password" placeholder={cfg._has_client_id ? '••••• saved •••••' : 'From Dev Dashboard → API credentials'}
              value={clientSecret} onChange={e => setClientSecret(e.target.value)} />
          </Field>
          <Field label="Static access token (shpat_…)">
            <Input type="password" placeholder={cfg._has_static_token ? '••••• saved •••••' : 'shpat_...'}
              value={staticToken} onChange={e => setStaticToken(e.target.value)} />
          </Field>
          <div className="flex gap-2 flex-wrap">
            <button onClick={handleSaveCredentials}
              className="px-4 py-2 bg-amber-500 hover:bg-amber-400 text-zinc-900 font-semibold text-sm rounded-lg transition-colors">
              Save credentials
            </button>
            <button onClick={handleTest} disabled={testing}
              className="flex items-center gap-1.5 px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-200
                         text-sm rounded-lg transition-colors disabled:opacity-50">
              {testing ? <Loader2 size={13} className="animate-spin" /> : null}
              Test connection
            </button>
            <button onClick={handleClearCredentials} disabled={clearing}
              className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-red-400 text-sm rounded-lg transition-colors">
              Clear credentials
            </button>
          </div>
          {testResult && (
            <span className={['flex items-center gap-1.5 text-sm',
              testResult.ok ? 'text-green-400' : 'text-red-400'].join(' ')}>
              {testResult.ok ? <CheckCircle size={14} /> : <XCircle size={14} />}
              {testResult.message}
            </span>
          )}
        </div>
      </Section>

      {/* Packing */}
      <Section title="Packing">
        <div className="grid grid-cols-2 gap-4">
          <Field label="Fill threshold — regular sheets (%)">
            <Input type="number" min={1} max={100} value={Math.round((cfg.fill_threshold ?? 0.2) * 100)}
              onChange={e => set('fill_threshold', +e.target.value / 100)} />
          </Field>
          <Field label="Fill threshold — iron-on sheets (%)">
            <Input type="number" min={1} max={100} value={Math.round((cfg.ironon_fill_threshold ?? 0.03) * 100)}
              onChange={e => set('ironon_fill_threshold', +e.target.value / 100)} />
          </Field>
        </div>
        <p className="text-xs text-zinc-500">
          A sheet is exported when it reaches this fill level. Iron-on sheets are always
          exported regardless of fill. Sheet dimensions and DPI are fixed constants —
          regular vinyl: 1200 × 600 mm (120 × 60 cm) at 96 DPI · iron-on: Letter (215.9 × 279.4 mm) at 300 DPI.
        </p>
      </Section>

      {/* Sheet counter */}
      <Section title="Sheet Counter">
        <p className="text-xs text-zinc-500 -mt-1">
          Set the counter to any number. The next export starts at that number + 1.
          Set to 0 to restart from sheet #001.
        </p>
        <div className="flex items-end gap-3 flex-wrap">
          <Field label="Reset counter to">
            <input type="number" min={0} value={resetValue}
              onChange={e => setResetValue(Math.max(0, +e.target.value))}
              className="bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm
                         text-zinc-100 focus:outline-none focus:border-amber-500 w-36" />
          </Field>
          <button onClick={handleResetSheetCount}
            className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-sm
                       rounded-lg transition-colors whitespace-nowrap mb-0.5">
            Apply
          </button>
          {resetMsg && <span className="text-xs text-amber-400 mb-0.5">{resetMsg}</span>}
        </div>
        <p className="text-xs text-zinc-500">
          Current next sheet = last counter value + 1. Check the doctor log or run output for the current value.
        </p>
      </Section>

      {/* Output folders */}
      <Section title="Output folders">
        <p className="text-xs text-zinc-500 -mt-1">
          Leave blank to use the defaults. When both are blank the app creates a
          <span className="font-mono text-zinc-400"> sheets/</span> and a sibling
          <span className="font-mono text-zinc-400"> reports/</span> folder inside
          its data directory.
        </p>
        <Field label="PNGs — sheets folder">
          <Input placeholder="e.g. C:\Users\nader\Desktop\sheets"
            value={cfg.output_folder ?? ''} onChange={e => set('output_folder', e.target.value)} />
        </Field>
        <Field label="Reports — Excel folder">
          <Input placeholder="e.g. C:\Users\nader\Desktop\reports (auto: sibling of sheets folder)"
            value={cfg.report_folder ?? ''} onChange={e => set('report_folder', e.target.value)} />
        </Field>
      </Section>

    </div>
  )
}
