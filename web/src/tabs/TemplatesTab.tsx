import { useState, useEffect } from 'react'
import { api } from '../api'
import type { TemplateInfo } from '../api'
import { CheckCircle, XCircle, AlertTriangle, RefreshCw, Loader2 } from 'lucide-react'

export default function TemplatesTab() {
  const [templates, setTemplates] = useState<TemplateInfo[]>([])
  const [loading, setLoading]     = useState(true)

  const load = () => {
    setLoading(true)
    api.listTemplates().then(t => { setTemplates(t); setLoading(false) })
  }

  useEffect(() => { load() }, [])

  return (
    <div className="flex flex-col gap-4 max-w-2xl">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-zinc-300">Template Readiness</h2>
        <button onClick={load} disabled={loading}
          className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-200 disabled:opacity-50">
          {loading ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
          Refresh
        </button>
      </div>

      {templates.map(t => (
        <div key={t.name} className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 flex flex-col gap-3">
          <div className="flex items-center gap-3">
            {t.ready
              ? <CheckCircle size={16} className="text-green-400 shrink-0" />
              : <XCircle size={16} className="text-red-400 shrink-0" />
            }
            <div>
              <div className="text-sm font-medium text-zinc-100">{t.name}</div>
              <div className={`text-xs ${t.ready ? 'text-green-500' : 'text-red-400'}`}>
                {t.ready ? 'Production ready' : 'Not ready'}
              </div>
            </div>
            {!t.fingerprint_ok && (
              <span className="ml-auto text-xs text-amber-400 flex items-center gap-1">
                <AlertTriangle size={12} /> Artwork changed
              </span>
            )}
          </div>

          {t.problems.length > 0 && (
            <div className="flex flex-col gap-1">
              {t.problems.map((p, i) => (
                <div key={i} className="text-xs text-red-400 bg-red-950/30 rounded px-2.5 py-1.5">{p}</div>
              ))}
            </div>
          )}

          {t.regions.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <div className="text-xs text-zinc-500 uppercase font-medium tracking-wider">Regions</div>
              {t.regions.map(r => (
                <div key={r.id} className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-zinc-500">{r.id}</span>
                    <span className="text-zinc-300">{r.label}</span>
                  </div>
                  <div className="text-zinc-600">{r.sku_match.join(', ')}</div>
                </div>
              ))}
            </div>
          )}

          {!t.has_sidecar && (
            <div className="text-xs text-zinc-500 bg-zinc-800 rounded px-3 py-2">
              No region sidecar — edit <code className="text-amber-400">data/regions/{t.name}.regions.json</code>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
