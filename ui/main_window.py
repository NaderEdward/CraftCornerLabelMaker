from __future__ import annotations

from PyQt6.QtWidgets import QMainWindow, QTabWidget

from ui.history_panel import HistoryPanel
from ui.production_panel import ProductionPanel
from ui.region_editor import RegionEditorTab
from ui.sheet_config_panel import SheetConfigPanel


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Craft Corner Label Maker")
        self.resize(1280, 860)

        tabs = QTabWidget()
        self.setCentralWidget(tabs)

        self.regions_tab = RegionEditorTab()
        self.production_tab = ProductionPanel()
        self.history_tab = HistoryPanel()
        self.settings_tab = SheetConfigPanel()

        tabs.addTab(self.regions_tab, "Regions")
        tabs.addTab(self.production_tab, "Production")
        tabs.addTab(self.history_tab, "History")
        tabs.addTab(self.settings_tab, "Settings")

        self._startup_maintenance()

    def _startup_maintenance(self) -> None:
        from core import paths as core_paths
        from core import settings as core_settings
        from orchestrator.journal import find_incomplete_runs
        from orchestrator.retention import prune_runs
        from ui.reconciliation_dialog import ReconciliationDialog

        incomplete = find_incomplete_runs(core_paths.runs_dir())
        actionable = [j for j in incomplete if j.untagged_order_ids()]
        if actionable:
            ReconciliationDialog(actionable, parent=self).exec()

        try:
            cfg = core_settings.load()
            prune_runs(core_paths.runs_dir(), cfg.get("run_retention_days", 30))
        except Exception:
            pass
