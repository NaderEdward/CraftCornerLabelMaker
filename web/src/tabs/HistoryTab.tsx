import { useState, useEffect } from 'react'
import { api } from '../api'
import type { ReportSheet } from '../api'
import { ExternalLink, RefreshCw, Loader2 } from 'lucide-react'

const PRODUCT_COLOURS = [
  'bg-blue-500', 'bg-amber-500', 'bg-green-500', 'bg-purple-500',
  'bg-red-500', 'bg-teal-500', 'bg-pink-500', 'bg-orange-500',
]

function SheetSchematic({
  tiles, sheetW, sheetH,
}: { tiles: ReportSheet['tiles']; sheetW: number; sheetH: number }) {
  const PREVIEW_W = 320
  const PREVIEW_H = Math.round(PREVIEW_W * sheetH / sheetW)
  const scaleX = PREVIEW_W / sheetW
  const scaleY = PREVIEW_H / sheetH

  return (
    <div className="border border-zinc-700 rounded overflow-hidden bg-zinc-950"
         style={{ width: PREVIEW_W, height: PREVIEW_H, position: 'relative', flexShrink: 0 }}>
      {tiles.map((t, i) => (
        <div key={i} style={{
          position: 'absolute',
          left:   t.x  * scaleX,
          top:    t.y  * scaleY,
          width:  t.w  * scaleX,
          height: t.h  * scaleY,
        }} className={`${PRODUCT_COLOURS[i % PRODUCT_COLOURS.length]} opacity-70 rounded-sm`} />
      ))}
    </div>
  )
}

export default function HistoryTab() {
  const [data, setData]     = useState<Awaited<ReturnType<typeof api.getReport>> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]   = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)

  // refresh=true forces the server to rebuild from the workbook instead of
  // serving report_data.json. Errors are surfaced rather than swallowed:
  // an empty history and a failed request look identical otherwise, which
  // is what hid the broken endpoint.
  const load = (refresh = false) => {
    setLoading(true)
    setError(null)
    api.getReport(refresh)
      .then(d => { setData(d); setLoading(false) })
      .catch(e => { setError(String(e?.message ?? e)); setLoading(false) })
  }

  useEffect(() => { load() }, [])

  const openHtml = () => window.open('/api/report/html?refresh=1', '_blank')

  if (loading) return (
    <div className="flex items-center gap-2 text-zinc-400 text-sm">
      <Loader2 size={14} className="animate-spin" /> Loading…
    </div>
  )

  if (error) return (
    <div className="flex flex-col gap-3 max-w-4xl">
      <h2 className="text-sm font-semibold text-zinc-300">Production History</h2>
      <div className="text-sm text-red-400 border border-red-900 bg-red-950/40 rounded p-3">
        Could not load production history: {error}
      </div>
      <button onClick={() => load(true)}
        className="self-start flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-200">
        <RefreshCw size={13} /> Retry
      </button>
    </div>
  )

  return (
    <div className="flex flex-col gap-4 max-w-4xl">
      <div className="flex items-center gap-3">
        <h2 className="text-sm font-semibold text-zinc-300">Production History</h2>
        <button onClick={() => load(true)}
          className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-200">
          <RefreshCw size={12} /> Refresh
        </button>
        <button onClick={openHtml}
          className="ml-auto flex items-center gap-1.5 text-xs text-zinc-400 hover:text-amber-400 transition-colors">
          <ExternalLink size={12} /> Open full report
        </button>
      </div>

      {data?.skipped_rows ? (
        <div className="text-xs text-amber-400 bg-amber-950/30 rounded px-3 py-2">
          ⚠ {data.skipped_rows} malformed row(s) skipped in the CSV
        </div>
      ) : null}

      {(!data?.sheets || data.sheets.length === 0) && (
        <div className="text-sm text-zinc-500">No sheets exported yet.</div>
      )}

      {data?.sheets.map(sheet => (
        <div key={sheet.no} className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
          {/* Sheet header */}
          <button onClick={() => setExpanded(e => e === sheet.no ? null : sheet.no)}
            className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-zinc-800/50 transition-colors">
            <div className="flex items-center gap-3">
              <span className="font-mono text-amber-400 text-sm font-semibold">#{sheet.no}</span>
              <span className="text-xs text-zinc-400">{sheet.date}</span>
              {sheet.forced && (
                <span className="text-xs bg-zinc-700 text-zinc-300 rounded px-1.5 py-0.5">force-exported</span>
              )}
            </div>
            <div className="flex items-center gap-3 text-xs text-zinc-400">
              <span>{sheet.rows.length} order{sheet.rows.length !== 1 ? 's' : ''}</span>
              <span className="font-medium text-zinc-300">{Math.round(sheet.fill * 100)}% fill</span>
              <div className="w-16 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                <div className="h-full bg-amber-500 rounded-full"
                     style={{ width: `${Math.round(sheet.fill * 100)}%` }} />
              </div>
            </div>
          </button>

          {expanded === sheet.no && (
            <div className="border-t border-zinc-800 p-4 flex gap-6">
              {sheet.tiles.length > 0 && (
                <SheetSchematic tiles={sheet.tiles} sheetW={420} sheetH={297} />
              )}
              <div className="flex-1 overflow-auto">
                <table className="text-xs w-full">
                  <thead>
                    <tr className="text-zinc-500 uppercase text-left">
                      <th className="pb-2 pr-3">Order</th>
                      <th className="pb-2 pr-3">Student</th>
                      <th className="pb-2 pr-3">School</th>
                      <th className="pb-2 pr-3">Product</th>
                      <th className="pb-2 text-right">Qty</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sheet.rows.map((r, i) => (
                      <tr key={i} className="text-zinc-300 border-t border-zinc-800/50">
                        <td className="py-1.5 pr-3 font-mono text-amber-400">{r.ord}</td>
                        <td className="py-1.5 pr-3">
                          {r.stu}
                          {r.ar && <span className="ml-1 text-zinc-500 text-xs" dir="rtl">{r.ar}</span>}
                        </td>
                        <td className="py-1.5 pr-3 text-zinc-400">{r.school}</td>
                        <td className="py-1.5 pr-3">{r.p}</td>
                        <td className="py-1.5 text-right">{r.q}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
