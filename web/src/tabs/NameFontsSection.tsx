/**
 * NameFontsSection.tsx
 * Drop-in section rendered inside ThemesTab below the artwork themes.
 * Lets the operator manage name_only fonts exactly like artwork themes:
 *  - Drag-drop or folder-scan font files (.otf / .ttf)
 *  - Set slug (= what customers order), stroke, gap, line-spacing
 *  - Edit params for existing entries
 *  - Remove (optionally delete file)
 */
import { useEffect, useRef, useState } from 'react'
import {
  Upload, FolderSearch, Trash2, RefreshCw, CheckCircle2,
  AlertTriangle, X, Settings,
} from 'lucide-react'

interface FontRow {
  slug:              string
  font_file:         string
  class_font_file:   string
  stroke_px:         number
  stroke_color:      string
  line_gap_mult:     number
  gap_from_name:     number
  force_uppercase:   boolean
  font_file_exists:  boolean
  class_font_exists: boolean
}

interface Candidate {
  source_path:       string
  original_name:     string
  suggested_slug:    string
  already_registered:boolean
  file_exists_in_dir:boolean
}

interface ImportResult {
  added:   string[]
  copied:  string[]
  skipped: string[]
  errors:  string[]
}

interface StagedFont {
  file:  File
  slug:  string
  stroke_px:      number
  stroke_color:   string
  line_gap_mult:  number
  gap_from_name:  number
  force_uppercase:boolean
}

const FONT_RE = /\.(otf|ttf|woff2?)$/i

function defaultParams() {
  return { stroke_px: 12, stroke_color: '#ffffff', line_gap_mult: 1.0, gap_from_name: 8, force_uppercase: true }
}

const card = 'rounded-xl border border-zinc-800 bg-zinc-900/50 p-4'
const btn  = 'px-3 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-40'
const inp  = 'bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-amber-500/60'

export default function NameFontsSection() {
  const [fonts, setFonts]           = useState<FontRow[]>([])
  const [dir, setDir]               = useState('')
  const [busy, setBusy]             = useState(false)
  const [result, setResult]         = useState<ImportResult | null>(null)
  const [error, setError]           = useState<string | null>(null)
  const [dragging, setDragging]     = useState(false)
  const [staged, setStaged]         = useState<StagedFont[]>([])
  const [folder, setFolder]         = useState('')
  const [candidates, setCandidates] = useState<Candidate[] | null>(null)
  const [selected, setSelected]     = useState<Set<string>>(new Set())
  const [slugMap, setSlugMap]       = useState<Record<string,string>>({})
  const [editing, setEditing]       = useState<string | null>(null)
  const [editData, setEditData]     = useState<Partial<FontRow>>({})
  const fileRef = useRef<HTMLInputElement>(null)

  async function refresh() {
    try {
      const r = await fetch('/api/name-fonts')
      if (!r.ok) throw new Error(await r.text())
      const d = await r.json()
      setFonts(d.fonts); setDir(d.name_fonts_dir)
    } catch (e: any) { setError(String(e.message || e)) }
  }
  useEffect(() => { refresh() }, [])

  // ── Drag & drop ──────────────────────────────────────────────────────────

  function addFiles(list: FileList | File[]) {
    const next: StagedFont[] = []
    for (const f of Array.from(list)) {
      if (!FONT_RE.test(f.name)) continue
      if (staged.find(s => s.file.name === f.name)) continue
      next.push({ file: f, slug: f.name.replace(/\.[^.]+$/,'').toLowerCase().replace(/[_-]+/g,' ').trim(), ...defaultParams() })
    }
    setStaged(p => [...p, ...next]); setResult(null)
  }

  async function uploadStaged() {
    if (!staged.length) return
    setBusy(true); setError(null); setResult(null)
    try {
      for (const s of staged) {
        const fd = new FormData()
        fd.append('files', s.file, s.file.name)
        fd.append('slug',           s.slug.trim())
        fd.append('stroke_px',      String(s.stroke_px))
        fd.append('stroke_color',   s.stroke_color)
        fd.append('line_gap_mult',  String(s.line_gap_mult))
        fd.append('gap_from_name',  String(s.gap_from_name))
        fd.append('force_uppercase',String(s.force_uppercase))
        const r = await fetch('/api/name-fonts/upload', { method: 'POST', body: fd })
        if (!r.ok) throw new Error(await r.text())
        const res = await r.json()
        setResult(res)
      }
      setStaged([]); await refresh()
    } catch (e: any) { setError(String(e.message || e)) }
    finally { setBusy(false) }
  }

  // ── Folder scan ──────────────────────────────────────────────────────────

  async function scanFolder() {
    if (!folder.trim()) return
    setBusy(true); setError(null); setResult(null); setCandidates(null)
    try {
      const r = await fetch('/api/name-fonts/scan-folder', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder }),
      })
      if (!r.ok) throw new Error(await r.text())
      const cs: Candidate[] = await r.json()
      setCandidates(cs)
      const map: Record<string,string> = {}
      cs.forEach(c => { map[c.original_name] = c.suggested_slug })
      setSlugMap(map)
      setSelected(new Set(cs.filter(c => !c.already_registered).map(c => c.source_path)))
    } catch (e: any) { setError(String(e.message || e)) }
    finally { setBusy(false) }
  }

  async function importSelected() {
    if (!candidates || !selected.size) return
    setBusy(true); setError(null); setResult(null)
    try {
      const paths   = [...selected]
      const slg_map: Record<string,string> = {}
      candidates.forEach(c => { slg_map[c.original_name] = slugMap[c.original_name] || c.suggested_slug })
      const r = await fetch('/api/name-fonts/import-paths', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paths, slug_map: slg_map }),
      })
      if (!r.ok) throw new Error(await r.text())
      setResult(await r.json()); setCandidates(null); setSelected(new Set())
      await refresh()
    } catch (e: any) { setError(String(e.message || e)) }
    finally { setBusy(false) }
  }

  // ── Edit params ───────────────────────────────────────────────────────────

  async function saveEdit(slug: string) {
    setBusy(true); setError(null)
    try {
      const row = fonts.find(f => f.slug === slug)
      const payload = { slug, font_file: row?.font_file || '', ...editData }
      const r = await fetch('/api/name-fonts/upsert', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!r.ok) throw new Error(await r.text())
      setEditing(null); await refresh()
    } catch (e: any) { setError(String(e.message || e)) }
    finally { setBusy(false) }
  }

  async function removeFont(slug: string, deleteFile: boolean) {
    if (!confirm(`Remove "${slug}"${deleteFile ? ' and delete font file?' : '?'}`)) return
    setBusy(true); setError(null)
    try {
      const r = await fetch('/api/name-fonts/remove', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ slug, delete_file: deleteFile }),
      })
      if (!r.ok) throw new Error(await r.text())
      await refresh()
    } catch (e: any) { setError(String(e.message || e)) }
    finally { setBusy(false) }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-5 mt-8 pt-8 border-t border-zinc-800">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            Name Fonts
            <span className="text-xs font-normal text-zinc-500 bg-zinc-800 px-2 py-0.5 rounded-full">
              name_only theme
            </span>
          </h2>
          <p className="text-sm text-zinc-500 mt-0.5">
            Decorative fonts for Chromatix-style labels — each slug is what customers order.
          </p>
          {dir && <div className="text-[11px] text-zinc-600 font-mono mt-1">fonts → {dir}</div>}
        </div>
        <button onClick={refresh} disabled={busy}
          className={`${btn} bg-zinc-800 hover:bg-zinc-700 flex items-center gap-2`}>
          <RefreshCw size={14} className={busy ? 'animate-spin' : ''} />Refresh
        </button>
      </div>

      {/* Drop zone */}
      <div className={card}>
        <div className="text-sm font-medium mb-3 flex items-center gap-2">
          <Upload size={15} className="text-amber-400" />Drop font files (.otf / .ttf)
        </div>
        <div
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={e => { e.preventDefault(); setDragging(false); if (e.dataTransfer.files) addFiles(e.dataTransfer.files) }}
          onClick={() => fileRef.current?.click()}
          className={['rounded-lg border-2 border-dashed p-6 text-center cursor-pointer transition-colors',
            dragging ? 'border-amber-500 bg-amber-500/5' : 'border-zinc-800 hover:border-zinc-700'].join(' ')}>
          <div className="text-sm text-zinc-400">Drop OTF / TTF files here, or click to browse</div>
          <div className="text-xs text-zinc-600 mt-1">Set the slug (customer theme name) before importing</div>
        </div>
        <input ref={fileRef} type="file" multiple accept=".otf,.ttf,.woff,.woff2"
          className="hidden" onChange={e => e.target.files && addFiles(e.target.files)} />

        {staged.length > 0 && (
          <div className="mt-4 space-y-3">
            {staged.map((s, i) => (
              <div key={s.file.name} className="rounded-lg border border-zinc-800 p-3 space-y-2">
                <div className="flex items-center gap-2 text-xs text-zinc-500 font-mono">
                  {s.file.name}
                  <button onClick={() => setStaged(p => p.filter((_,j) => j !== i))}
                    className="ml-auto text-zinc-600 hover:text-red-400"><X size={14}/></button>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <label className="flex flex-col gap-1">
                    <span className="text-[10px] text-zinc-500">Slug (customer theme name)</span>
                    <input value={s.slug} onChange={e => setStaged(p => p.map((x,j) => j===i ? {...x,slug:e.target.value} : x))}
                      className={`${inp} py-1`} placeholder="e.g. cutout chromatix" />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-[10px] text-zinc-500">Stroke px</span>
                    <input type="number" value={s.stroke_px} min={1} max={30}
                      onChange={e => setStaged(p => p.map((x,j) => j===i ? {...x,stroke_px:+e.target.value} : x))}
                      className={`${inp} py-1`} />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-[10px] text-zinc-500">Stroke colour</span>
                    <div className="flex gap-2 items-center">
                      <input type="color" value={s.stroke_color}
                        onChange={e => setStaged(p => p.map((x,j) => j===i ? {...x,stroke_color:e.target.value} : x))}
                        className="h-8 w-10 rounded border border-zinc-700 bg-transparent cursor-pointer" />
                      <span className="text-xs text-zinc-500 font-mono">{s.stroke_color}</span>
                    </div>
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-[10px] text-zinc-500">Gap from name (px)</span>
                    <input type="number" value={s.gap_from_name} min={-50} max={200}
                      onChange={e => setStaged(p => p.map((x,j) => j===i ? {...x,gap_from_name:+e.target.value} : x))}
                      className={`${inp} py-1`} />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-[10px] text-zinc-500">Line spacing ×</span>
                    <input type="number" value={s.line_gap_mult} step={0.1} min={-2} max={3}
                      onChange={e => setStaged(p => p.map((x,j) => j===i ? {...x,line_gap_mult:+e.target.value} : x))}
                      className={`${inp} py-1`} />
                  </label>
                  <label className="flex items-center gap-2 text-sm text-zinc-300 mt-4">
                    <input type="checkbox" checked={s.force_uppercase}
                      onChange={e => setStaged(p => p.map((x,j) => j===i ? {...x,force_uppercase:e.target.checked} : x))}
                      className="accent-amber-500" />
                    Force uppercase
                  </label>
                </div>
              </div>
            ))}
            <div className="flex gap-2 pt-1">
              <button onClick={uploadStaged} disabled={busy}
                className={`${btn} bg-amber-500 text-zinc-900 hover:bg-amber-400`}>
                Import {staged.length} font{staged.length > 1 ? 's' : ''}
              </button>
              <button onClick={() => setStaged([])} disabled={busy}
                className={`${btn} bg-zinc-800 hover:bg-zinc-700`}>Clear</button>
            </div>
          </div>
        )}
      </div>

      {/* Folder scan */}
      <div className={card}>
        <div className="text-sm font-medium mb-3 flex items-center gap-2">
          <FolderSearch size={15} className="text-amber-400" />
          Scan "Names" folder
        </div>
        <div className="flex gap-2">
          <input value={folder} onChange={e => setFolder(e.target.value)}
            placeholder={`C:\\Users\\nadin\\All themes\\Names`}
            className={`${inp} flex-1 font-mono text-xs`} />
          <button onClick={scanFolder} disabled={busy || !folder.trim()}
            className={`${btn} bg-zinc-800 hover:bg-zinc-700`}>Scan</button>
        </div>
        {candidates && (
          <div className="mt-4">
            {candidates.length === 0
              ? <div className="text-sm text-zinc-500">No font files found.</div>
              : <>
                  <div className="text-xs text-zinc-500 mb-2">
                    {candidates.length} file(s) · {selected.size} selected
                  </div>
                  <div className="max-h-60 overflow-auto rounded-lg border border-zinc-800 divide-y divide-zinc-800/70">
                    {candidates.map(c => (
                      <label key={c.source_path}
                        className="flex items-center gap-3 px-3 py-2 text-sm hover:bg-zinc-800/40 cursor-pointer">
                        <input type="checkbox" checked={selected.has(c.source_path)}
                          onChange={e => setSelected(prev => {
                            const n = new Set(prev)
                            e.target.checked ? n.add(c.source_path) : n.delete(c.source_path)
                            return n
                          })} className="accent-amber-500" />
                        <span className="text-zinc-500 text-xs font-mono truncate flex-1">{c.original_name}</span>
                        <input value={slugMap[c.original_name] || c.suggested_slug}
                          onChange={e => setSlugMap(m => ({...m, [c.original_name]: e.target.value}))}
                          onClick={e => e.stopPropagation()}
                          className={`${inp} w-44 py-0.5 text-xs`} placeholder="slug" />
                        {c.already_registered && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400">registered</span>)}
                      </label>
                    ))}
                  </div>
                  <button onClick={importSelected} disabled={busy || !selected.size}
                    className={`${btn} bg-amber-500 text-zinc-900 hover:bg-amber-400 mt-3`}>
                    Import {selected.size} selected
                  </button>
                </>
            }
          </div>
        )}
      </div>

      {/* Result / error */}
      {error && (
        <div className="rounded-xl border border-red-900/60 bg-red-950/30 p-4 text-sm text-red-300 flex items-start gap-2">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />{error}
        </div>
      )}
      {result && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 text-sm space-y-1">
          {result.added.map((s,i) => <div key={i} className="text-emerald-400 flex gap-2"><CheckCircle2 size={14} className="mt-0.5"/>Added slug: {s}</div>)}
          {result.copied.map((s,i) => <div key={i} className="text-zinc-400">Copied: {s}</div>)}
          {result.skipped.map((s,i) => <div key={i} className="text-amber-400 text-xs">Skipped — {s}</div>)}
          {result.errors.map((s,i) => <div key={i} className="text-red-400 text-xs">Error — {s}</div>)}
        </div>
      )}

      {/* Registered fonts list */}
      <div className={card}>
        <div className="text-sm font-medium mb-3">Registered name fonts · {fonts.length}</div>
        {fonts.length === 0
          ? <div className="text-sm text-zinc-500">No fonts registered yet.</div>
          : (
            <div className="rounded-lg border border-zinc-800 divide-y divide-zinc-800/70">
              {fonts.map(f => (
                <div key={f.slug}>
                  <div className="flex items-center gap-3 px-3 py-2 text-sm group">
                    {f.font_file_exists
                      ? <CheckCircle2 size={14} className="text-emerald-500 shrink-0"/>
                      : <AlertTriangle size={14} className="text-amber-500 shrink-0"/>}
                    <span className="font-medium flex-1">{f.slug}</span>
                    <span className="text-xs text-zinc-600 font-mono truncate max-w-xs">{f.font_file}</span>
                    <button onClick={() => { setEditing(editing===f.slug ? null : f.slug); setEditData({...f}) }}
                      className="opacity-0 group-hover:opacity-100 text-zinc-600 hover:text-amber-400">
                      <Settings size={14}/>
                    </button>
                    <button onClick={() => removeFont(f.slug, false)} disabled={busy}
                      title="Remove from registry (keep file)"
                      className="opacity-0 group-hover:opacity-100 text-zinc-600 hover:text-amber-400">
                      <X size={15}/>
                    </button>
                    <button onClick={() => removeFont(f.slug, true)} disabled={busy}
                      title="Remove and delete font file"
                      className="opacity-0 group-hover:opacity-100 text-zinc-600 hover:text-red-400">
                      <Trash2 size={14}/>
                    </button>
                  </div>

                  {editing === f.slug && (
                    <div className="px-3 pb-3 bg-zinc-900/60 grid grid-cols-2 gap-3">
                      <label className="flex flex-col gap-1">
                        <span className="text-[10px] text-zinc-500">Stroke px</span>
                        <input type="number" value={editData.stroke_px ?? f.stroke_px} min={1} max={30}
                          onChange={e => setEditData(d => ({...d, stroke_px:+e.target.value}))}
                          className={`${inp} py-1`} />
                      </label>
                      <label className="flex flex-col gap-1">
                        <span className="text-[10px] text-zinc-500">Stroke colour</span>
                        <div className="flex gap-2 items-center">
                          <input type="color" value={editData.stroke_color ?? f.stroke_color}
                            onChange={e => setEditData(d => ({...d, stroke_color:e.target.value}))}
                            className="h-8 w-10 rounded border border-zinc-700 bg-transparent cursor-pointer" />
                          <span className="text-xs text-zinc-500 font-mono">{editData.stroke_color ?? f.stroke_color}</span>
                        </div>
                      </label>
                      <label className="flex flex-col gap-1">
                        <span className="text-[10px] text-zinc-500">Gap from name (px)</span>
                        <input type="number" value={editData.gap_from_name ?? f.gap_from_name} min={-50} max={200}
                          onChange={e => setEditData(d => ({...d, gap_from_name:+e.target.value}))}
                          className={`${inp} py-1`} />
                      </label>
                      <label className="flex flex-col gap-1">
                        <span className="text-[10px] text-zinc-500">Line spacing ×</span>
                        <input type="number" value={editData.line_gap_mult ?? f.line_gap_mult} step={0.1} min={-2} max={3}
                          onChange={e => setEditData(d => ({...d, line_gap_mult:+e.target.value}))}
                          className={`${inp} py-1`} />
                      </label>
                      <div className="col-span-2 flex gap-2 pt-1">
                        <button onClick={() => saveEdit(f.slug)} disabled={busy}
                          className={`${btn} bg-amber-500 text-zinc-900 hover:bg-amber-400`}>Save</button>
                        <button onClick={() => setEditing(null)} disabled={busy}
                          className={`${btn} bg-zinc-800 hover:bg-zinc-700`}>Cancel</button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
      </div>
    </div>
  )
}
