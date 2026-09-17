import NameFontsSection from './NameFontsSection'
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Upload, FolderSearch, Trash2, RefreshCw, AlertTriangle,
  CheckCircle2, Image as ImageIcon, X,
} from 'lucide-react'

// ── Types ───────────────────────────────────────────────────────────────

interface ThemeRow {
  theme: string
  has_background: boolean
  background_file: string | null
}

interface ThemesPayload {
  categories: string[]
  labels: Record<string, string>
  themes: Record<string, ThemeRow[]>
  themes_list_path: string
  backgrounds_write_root: string
}

interface Candidate {
  source_path: string
  original_name: string
  theme: string
  already_listed: boolean
  background_exists: boolean
}

interface ImportResult {
  added: string[]
  copied: string[]
  skipped: string[]
  errors: string[]
}

// A file staged for upload, with its editable derived theme name.
interface Staged {
  file: File
  theme: string
}

const IMAGE_RE = /\.(png|jpe?g)$/i

// Mirrors core/theme_admin.derive_theme_name so the operator sees the exact
// name that will be written before committing. Kept in sync deliberately —
// the server re-derives anyway, this is preview only.
const STRIP_PREFIXES = ['extras', 'extra', 'vp']
const STRIP_SUFFIXES = ['copy', 'empty', 'blank', 'final', 'new']

function deriveThemeName(filename: string): string {
  let s = filename.replace(/\.[^.]+$/, '').toLowerCase()
  s = s.replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim()
  for (const p of STRIP_PREFIXES) {
    if (s.startsWith(p + ' ')) { s = s.slice(p.length + 1).trim(); break }
  }
  let changed = true
  while (changed) {
    changed = false
    for (const suf of STRIP_SUFFIXES) {
      if (s.endsWith(' ' + suf)) { s = s.slice(0, -(suf.length + 1)).trim(); changed = true }
    }
  }
  return s
}

// ── Component ───────────────────────────────────────────────────────────

export default function ThemesTab() {
  const [data, setData] = useState<ThemesPayload | null>(null)
  const [category, setCategory] = useState('signs')
  const [isExtras, setIsExtras] = useState(false)
  const [overwrite, setOverwrite] = useState(false)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [allThemesPath, setAllThemesPath] = useState('')
  const [allThemesScanning, setAllThemesScanning] = useState(false)
  const [allThemesScanResult, setAllThemesScanResult] = useState<Record<string,any> | null>(null)

  const [staged, setStaged] = useState<Staged[]>([])
  const [dragging, setDragging] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  const [folder, setFolder] = useState('')
  const [recursive, setRecursive] = useState(false)
  const [candidates, setCandidates] = useState<Candidate[] | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())

  async function scanAll() {
    if (!allThemesPath.trim()) return
    setAllThemesScanning(true); setError(null); setAllThemesScanResult(null)
    try {
      const r = await fetch('/api/scan-all-themes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder: allThemesPath }),
      })
      if (!r.ok) throw new Error(await r.text())
      setAllThemesScanResult(await r.json())
      await refresh()
    } catch (e: any) { setError(String(e.message || e)) }
    finally { setAllThemesScanning(false) }
  }

  async function refresh() {
    try {
      const r = await fetch('/api/themes')
      if (!r.ok) throw new Error(await r.text())
      setData(await r.json())
    } catch (e: any) { setError(String(e.message || e)) }
  }
  useEffect(() => { refresh() }, [])

  const rows = data?.themes[category] ?? []
  const missingCount = useMemo(
    () => rows.filter(r => !r.has_background).length, [rows])

  // ── Drag & drop / file picker ────────────────────────────────────────

  function addFiles(list: FileList | File[]) {
    const next: Staged[] = []
    for (const f of Array.from(list)) {
      if (!IMAGE_RE.test(f.name)) continue
      next.push({ file: f, theme: deriveThemeName(f.name) })
    }
    setStaged(prev => {
      const seen = new Set(prev.map(s => s.file.name))
      return [...prev, ...next.filter(n => !seen.has(n.file.name))]
    })
    setResult(null)
  }

  async function uploadStaged() {
    if (!staged.length) return
    setBusy(true); setError(null); setResult(null)
    try {
      const fd = new FormData()
      fd.append('category', category)
      fd.append('is_extras', String(isExtras))
      fd.append('overwrite', String(overwrite))
      const overrides: Record<string, string> = {}
      for (const s of staged) {
        fd.append('files', s.file, s.file.name)
        overrides[s.file.name] = s.theme.trim()
      }
      fd.append('themes', JSON.stringify(overrides))

      const r = await fetch('/api/themes/upload', { method: 'POST', body: fd })
      if (!r.ok) throw new Error(await r.text())
      setResult(await r.json())
      setStaged([])
      await refresh()
    } catch (e: any) { setError(String(e.message || e)) }
    finally { setBusy(false) }
  }

  // ── Folder scan / import ─────────────────────────────────────────────

  async function scanFolder() {
    if (!folder.trim()) return
    setBusy(true); setError(null); setResult(null); setCandidates(null)
    try {
      const r = await fetch('/api/themes/scan-folder', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder, category, recursive }),
      })
      if (!r.ok) throw new Error(await r.text())
      const cs: Candidate[] = await r.json()
      setCandidates(cs)
      // Preselect only what isn't already in place — the common intent when
      // re-pointing at a folder you've imported from before.
      setSelected(new Set(cs.filter(c => !c.already_listed || !c.background_exists)
                            .map(c => c.source_path)))
    } catch (e: any) { setError(String(e.message || e)) }
    finally { setBusy(false) }
  }

  async function importSelected() {
    if (!candidates || !selected.size) return
    setBusy(true); setError(null); setResult(null)
    try {
      const r = await fetch('/api/themes/import-paths', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          paths: [...selected], category,
          is_extras: isExtras, overwrite,
        }),
      })
      if (!r.ok) throw new Error(await r.text())
      setResult(await r.json())
      setCandidates(null); setSelected(new Set())
      await refresh()
    } catch (e: any) { setError(String(e.message || e)) }
    finally { setBusy(false) }
  }

  async function removeTheme(theme: string, deleteFile: boolean) {
    const msg = deleteFile
      ? `Remove "${theme}" and DELETE its background file?`
      : `Remove "${theme}" from the theme list? (background file kept)`
    if (!confirm(msg)) return
    setBusy(true); setError(null)
    try {
      const r = await fetch('/api/themes/remove', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ theme, category, delete_file: deleteFile }),
      })
      if (!r.ok) throw new Error(await r.text())
      await refresh()
    } catch (e: any) { setError(String(e.message || e)) }
    finally { setBusy(false) }
  }

  // ── Render ───────────────────────────────────────────────────────────

  const card = 'rounded-xl border border-zinc-800 bg-zinc-900/50 p-4'
  const btn = 'px-3 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-40'
  const input = 'bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm ' +
                'focus:outline-none focus:border-amber-500/60'

  return (
    <div className="max-w-5xl mx-auto space-y-5">

      {/* ── Scan All Themes folder ── */}
      <div className={card + " border-amber-500/30 bg-amber-500/5"}>
        <div className="text-sm font-semibold mb-2 flex items-center gap-2">
          <FolderSearch size={15} className="text-amber-400" />
          Scan All Themes Folder
          <span className="text-xs font-normal text-zinc-500">
            — imports signs, stitches, plain_signs, plain_stitches, name_fonts in one go
          </span>
        </div>
        <div className="flex gap-2">
          <input
            value={allThemesPath}
            onChange={e => setAllThemesPath(e.target.value)}
            placeholder={`C:\\Users\\nadin\\All themes`}
            className={input + ' flex-1 font-mono text-xs'}
          />
          <button onClick={scanAll} disabled={allThemesScanning || !allThemesPath.trim()}
            className={`${btn} bg-amber-500 text-zinc-900 hover:bg-amber-400 disabled:opacity-40`}>
            {allThemesScanning ? 'Scanning…' : 'Scan & Import'}
          </button>
        </div>
        {allThemesScanResult && (
          <div className="mt-3 space-y-1 text-xs">
            {Object.entries(allThemesScanResult!).map(([cat, res]: [string, any]) => (
              <div key={cat} className="flex gap-3 items-start">
                <span className="text-zinc-400 font-mono w-24 shrink-0">{cat}</span>
                <span className="text-emerald-400">{res.added?.length ?? 0} added</span>
                <span className="text-zinc-500">{res.copied?.length ?? 0} copied</span>
                {res.skipped?.length > 0 && <span className="text-amber-400">{res.skipped[0]}</span>}
                {res.errors?.length > 0 && <span className="text-red-400">{res.errors[0]}</span>}
              </div>
            ))}
          </div>
        )}
      </div>

            <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">Themes</h2>
          <p className="text-sm text-zinc-500 mt-0.5">
            Import background artwork and keep the theme list in sync.
          </p>
        </div>
        <button onClick={refresh} disabled={busy}
          className={`${btn} bg-zinc-800 hover:bg-zinc-700 flex items-center gap-2`}>
          <RefreshCw size={14} className={busy ? 'animate-spin' : ''} />Refresh
        </button>
      </div>

      {/* Category + options */}
      <div className={card}>
        <div className="flex flex-wrap items-end gap-4">
          <label className="flex flex-col gap-1.5">
            <span className="text-xs text-zinc-500 font-medium">Category</span>
            <select value={category} onChange={e => {
              setCategory(e.target.value); setCandidates(null); setResult(null)
            }} className={input}>
              {data?.categories.map(c => (
                <option key={c} value={c}>{data.labels[c]}</option>
              ))}
            </select>
          </label>

          <label className="flex items-center gap-2 text-sm text-zinc-300 pb-2.5">
            <input type="checkbox" checked={isExtras}
              onChange={e => setIsExtras(e.target.checked)}
              className="accent-amber-500" />
            Extras artwork <span className="text-zinc-600 text-xs">(names as "Extras …")</span>
          </label>

          <label className="flex items-center gap-2 text-sm text-zinc-300 pb-2.5">
            <input type="checkbox" checked={overwrite}
              onChange={e => setOverwrite(e.target.checked)}
              className="accent-amber-500" />
            Overwrite existing files
          </label>
        </div>

        {data && (
          <div className="mt-3 pt-3 border-t border-zinc-800/70 text-[11px] text-zinc-600 space-y-0.5 font-mono">
            <div>list → {data.themes_list_path}</div>
            <div>images → {data.backgrounds_write_root}\{category}</div>
          </div>
        )}
      </div>

      {/* Drag & drop */}
      <div className={card}>
        <div className="text-sm font-medium mb-3 flex items-center gap-2">
          <Upload size={15} className="text-amber-400" />Drop files
        </div>

        <div
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={e => {
            e.preventDefault(); setDragging(false)
            if (e.dataTransfer.files) addFiles(e.dataTransfer.files)
          }}
          onClick={() => fileInput.current?.click()}
          className={['rounded-lg border-2 border-dashed p-8 text-center cursor-pointer transition-colors',
            dragging ? 'border-amber-500 bg-amber-500/5' : 'border-zinc-800 hover:border-zinc-700'
          ].join(' ')}>
          <ImageIcon size={22} className="mx-auto text-zinc-600 mb-2" />
          <div className="text-sm text-zinc-400">
            Drop PNG / JPG files here, or click to browse
          </div>
          <div className="text-xs text-zinc-600 mt-1">
            Theme names are derived automatically — edit them below before importing
          </div>
        </div>
        <input ref={fileInput} type="file" multiple accept=".png,.jpg,.jpeg"
          className="hidden"
          onChange={e => e.target.files && addFiles(e.target.files)} />

        {staged.length > 0 && (
          <div className="mt-4 space-y-2">
            {staged.map((s, i) => (
              <div key={s.file.name} className="flex items-center gap-3 text-sm">
                <span className="flex-1 truncate text-zinc-500 text-xs font-mono">
                  {s.file.name}
                </span>
                <span className="text-zinc-600">→</span>
                <input value={s.theme}
                  onChange={e => setStaged(p => p.map((x, j) =>
                    j === i ? { ...x, theme: e.target.value } : x))}
                  className={`${input} w-56 py-1`} />
                <button onClick={() => setStaged(p => p.filter((_, j) => j !== i))}
                  className="text-zinc-600 hover:text-red-400"><X size={15} /></button>
              </div>
            ))}
            <div className="flex gap-2 pt-2">
              <button onClick={uploadStaged} disabled={busy}
                className={`${btn} bg-amber-500 text-zinc-900 hover:bg-amber-400`}>
                Import {staged.length} file{staged.length > 1 ? 's' : ''}
              </button>
              <button onClick={() => setStaged([])} disabled={busy}
                className={`${btn} bg-zinc-800 hover:bg-zinc-700`}>Clear</button>
            </div>
          </div>
        )}
      </div>

      {/* Folder import */}
      <div className={card}>
        <div className="text-sm font-medium mb-3 flex items-center gap-2">
          <FolderSearch size={15} className="text-amber-400" />Import from a folder
        </div>
        <div className="flex gap-2">
          <input value={folder} onChange={e => setFolder(e.target.value)}
            placeholder="A:\All themes\new artwork"
            className={`${input} flex-1 font-mono text-xs`} />
          <label className="flex items-center gap-2 text-sm text-zinc-300 px-1">
            <input type="checkbox" checked={recursive}
              onChange={e => setRecursive(e.target.checked)}
              className="accent-amber-500" />
            Subfolders
          </label>
          <button onClick={scanFolder} disabled={busy || !folder.trim()}
            className={`${btn} bg-zinc-800 hover:bg-zinc-700`}>Scan</button>
        </div>

        {candidates && (
          <div className="mt-4">
            {candidates.length === 0 ? (
              <div className="text-sm text-zinc-500">No image files found in that folder.</div>
            ) : (
              <>
                <div className="text-xs text-zinc-500 mb-2">
                  {candidates.length} file(s) found · {selected.size} selected
                </div>
                <div className="max-h-72 overflow-auto rounded-lg border border-zinc-800 divide-y divide-zinc-800/70">
                  {candidates.map(c => (
                    <label key={c.source_path}
                      className="flex items-center gap-3 px-3 py-2 text-sm hover:bg-zinc-800/40 cursor-pointer">
                      <input type="checkbox" checked={selected.has(c.source_path)}
                        onChange={e => setSelected(prev => {
                          const n = new Set(prev)
                          e.target.checked ? n.add(c.source_path) : n.delete(c.source_path)
                          return n
                        })}
                        className="accent-amber-500" />
                      <span className="flex-1 truncate text-zinc-500 text-xs font-mono">
                        {c.original_name}
                      </span>
                      <span className="text-zinc-300 w-48 truncate">{c.theme}</span>
                      {c.already_listed && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400">
                          listed
                        </span>
                      )}
                      {c.background_exists && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400">
                          file exists
                        </span>
                      )}
                    </label>
                  ))}
                </div>
                <button onClick={importSelected} disabled={busy || !selected.size}
                  className={`${btn} bg-amber-500 text-zinc-900 hover:bg-amber-400 mt-3`}>
                  Import {selected.size} selected
                </button>
              </>
            )}
          </div>
        )}
      </div>

      {/* Result / error */}
      {error && (
        <div className="rounded-xl border border-red-900/60 bg-red-950/30 p-4 text-sm text-red-300
                        flex items-start gap-2">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <div className="whitespace-pre-wrap break-all">{error}</div>
        </div>
      )}

      {result && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 text-sm space-y-2">
          {result.added.length > 0 && (
            <div className="flex gap-2 text-emerald-400">
              <CheckCircle2 size={16} className="mt-0.5 shrink-0" />
              <span>Added to theme list: {result.added.join(', ')}</span>
            </div>
          )}
          {result.copied.length > 0 && (
            <div className="text-zinc-400">Copied {result.copied.length} file(s).</div>
          )}
          {result.skipped.map((s, i) => (
            <div key={i} className="text-amber-400/90 text-xs">Skipped — {s}</div>
          ))}
          {result.errors.map((s, i) => (
            <div key={i} className="text-red-400 text-xs">Error — {s}</div>
          ))}
          {!result.added.length && !result.copied.length &&
           !result.skipped.length && !result.errors.length && (
            <div className="text-zinc-500">Nothing to do.</div>
          )}
        </div>
      )}

      {/* Name Fonts — below artwork themes */}
      <NameFontsSection />

      {/* Current themes */}
      <div className={card}>
        <div className="flex items-center justify-between mb-3">
          <div className="text-sm font-medium">
            {data?.labels[category]} · {rows.length} theme(s)
          </div>
          {missingCount > 0 && (
            <div className="text-xs text-amber-400 flex items-center gap-1.5">
              <AlertTriangle size={13} />
              {missingCount} listed with no background file
            </div>
          )}
        </div>

        {rows.length === 0 ? (
          <div className="text-sm text-zinc-500">No themes in this category yet.</div>
        ) : (
          <div className="rounded-lg border border-zinc-800 divide-y divide-zinc-800/70">
            {rows.map(r => (
              <div key={r.theme}
                className="flex items-center gap-3 px-3 py-2 text-sm group">
                {r.has_background
                  ? <CheckCircle2 size={14} className="text-emerald-500 shrink-0" />
                  : <AlertTriangle size={14} className="text-amber-500 shrink-0" />}
                <span className="flex-1">{r.theme}</span>
                <span className="text-xs text-zinc-600 font-mono truncate max-w-xs">
                  {r.background_file ?? 'no background found'}
                </span>
                <button onClick={() => removeTheme(r.theme, false)} disabled={busy}
                  title="Remove from list (keep file)"
                  className="opacity-0 group-hover:opacity-100 text-zinc-600 hover:text-amber-400">
                  <X size={15} />
                </button>
                <button onClick={() => removeTheme(r.theme, true)} disabled={busy}
                  title="Remove and delete background file"
                  className="opacity-0 group-hover:opacity-100 text-zinc-600 hover:text-red-400">
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
