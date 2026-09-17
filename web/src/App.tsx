import { useState } from 'react'
import { Settings2, ShoppingBag, LayoutGrid, BarChart2, Palette } from 'lucide-react'
import ProductionTab from './tabs/ProductionTab'
import SettingsTab from './tabs/SettingsTab'
import TemplatesTab from './tabs/TemplatesTab'
import HistoryTab from './tabs/HistoryTab'
import ThemesTab from './tabs/ThemesTab'

const TABS = [
  { id: 'production', label: 'Production', Icon: ShoppingBag },
  { id: 'templates',  label: 'Templates',  Icon: LayoutGrid  },
  { id: 'themes',     label: 'Themes',     Icon: Palette     },
  { id: 'history',    label: 'History',    Icon: BarChart2   },
  { id: 'settings',   label: 'Settings',   Icon: Settings2   },
] as const
type TabId = typeof TABS[number]['id']

export default function App() {
  const [active, setActive] = useState<TabId>('production')
  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col">
      <header className="sticky top-0 z-20 backdrop-blur bg-zinc-950/85 border-b border-zinc-800/80">
        <div className="px-6 py-3 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-amber-400 to-amber-600
                          flex items-center justify-center text-zinc-900 font-bold text-xs shadow-lg shadow-amber-500/20">
            CC
          </div>
          <div className="leading-tight">
            <div className="font-semibold text-sm tracking-tight">Craft Corner</div>
            <div className="text-[11px] text-zinc-500">Label Maker</div>
          </div>
        </div>
        <nav className="flex px-4 gap-1">
          {TABS.map(({ id, label, Icon }) => (
            <button key={id} onClick={() => setActive(id)}
              className={['flex items-center gap-2 px-3.5 py-2.5 text-sm font-medium border-b-2 transition-colors',
                active === id
                  ? 'border-amber-500 text-amber-400'
                  : 'border-transparent text-zinc-500 hover:text-zinc-200'].join(' ')}>
              <Icon size={15} />{label}
            </button>
          ))}
        </nav>
      </header>
      <main className="flex-1 overflow-auto p-6">
        {active === 'production' && <ProductionTab />}
        {active === 'templates'  && <TemplatesTab />}
        {active === 'themes'     && <ThemesTab />}
        {active === 'history'    && <HistoryTab />}
        {active === 'settings'   && <SettingsTab />}
      </main>
    </div>
  )
}
