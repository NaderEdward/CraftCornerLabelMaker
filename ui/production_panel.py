from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QMessageBox, QProgressBar,
    QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from core import paths as core_paths
from core import settings as core_settings
from orchestrator.pipeline import Pipeline, RunConfig


class _Worker(QThread):
    progress = pyqtSignal(str, int, int)
    finished_ok = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, pipeline: Pipeline, action: str, force: bool = False):
        super().__init__()
        self.pipeline = pipeline
        self.action = action
        self.force = force

    def run(self) -> None:
        try:
            self.pipeline.on_progress = lambda stage, cur, total: self.progress.emit(stage, cur, total)
            if self.action == "fetch":
                result = self.pipeline.fetch()
            elif self.action == "run_all":
                result = self.pipeline.run_all(force=self.force)
            elif self.action == "pack_preview":
                self.pipeline.transform()
                self.pipeline.extract()
                result = self.pipeline.pack()
            elif self.action == "export":
                result = self.pipeline.export(force=self.force)
            else:
                raise ValueError(f"Unknown action '{self.action}'")
            self.finished_ok.emit(result)
        except Exception as e:
            self.failed.emit(str(e))


class ProductionPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._pipeline: Optional[Pipeline] = None
        self._worker: Optional[_Worker] = None

        layout = QVBoxLayout(self)

        top_bar = QHBoxLayout()
        self.fetch_btn = QPushButton("Fetch Orders")
        self.fetch_btn.clicked.connect(self._on_fetch)
        top_bar.addWidget(self.fetch_btn)
        self.status_label = QLabel("No fetch yet")
        top_bar.addWidget(self.status_label, 1)
        layout.addLayout(top_bar)

        self.order_list = QListWidget()
        layout.addWidget(self.order_list, 2)

        self.warnings_view = QTextEdit()
        self.warnings_view.setReadOnly(True)
        self.warnings_view.setMaximumHeight(120)
        layout.addWidget(self.warnings_view)

        self.progress = QProgressBar()
        layout.addWidget(self.progress)

        bottom_bar = QHBoxLayout()
        self.export_btn = QPushButton("Export Ready Sheets")
        self.export_btn.clicked.connect(lambda: self._on_export(force=False))
        self.force_btn = QPushButton("Force Export All")
        self.force_btn.clicked.connect(lambda: self._on_export(force=True))
        bottom_bar.addWidget(self.export_btn)
        bottom_bar.addWidget(self.force_btn)
        layout.addLayout(bottom_bar)

    def _build_config(self) -> RunConfig:
        cfg = core_settings.load()
        return RunConfig(
            shopify_domain=cfg["shopify_domain"],
            shopify_api_version=cfg["shopify_api_version"],
            in_progress_tag=cfg["in_progress_tag"],
            output_folder=core_paths.default_output_folder(),
            report_folder=core_paths.default_report_folder(),
            sheet_width_mm=cfg["sheet_width_mm"],
            sheet_height_mm=cfg["sheet_height_mm"],
            margin_mm={
                "t": cfg["margin_t_mm"], "b": cfg["margin_b_mm"],
                "l": cfg["margin_l_mm"], "r": cfg["margin_r_mm"],
            },
            inter_tile_gap_mm=cfg["inter_tile_gap_mm"],
            sheet_dpi=cfg["sheet_dpi"],
            fill_threshold=cfg["fill_threshold"],
            pack_strategy=cfg["pack_strategy"],
            label_tiles=cfg["label_tiles"],
            ironon_sheet_width_mm=cfg.get("ironon_sheet_width_mm", 215.9),
        ironon_sheet_height_mm=cfg.get("ironon_sheet_height_mm", 279.4),
        ironon_sheet_dpi=cfg.get("ironon_sheet_dpi", 300),
        ironon_fill_threshold=cfg.get("ironon_fill_threshold", 0.03),
        field_mapping=cfg["field_mapping"],
        enabler_map=cfg.get("enabler_map", {"OC": "Class", "OS": "school name", "OP": "text-5"}),
            last_sheet_number=cfg.get("last_sheet_number", 0),
        )

    def _on_fetch(self) -> None:
        self._pipeline = Pipeline(self._build_config())
        self._worker = _Worker(self._pipeline, "fetch")
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_fetch_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, stage: str, current: int, total: int) -> None:
        self.status_label.setText(f"{stage}: {current}/{total}")
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(current)

    def _on_fetch_done(self, _path) -> None:
        self.status_label.setText("Fetched. Building pack preview…")
        self._worker = _Worker(self._pipeline, "pack_preview")
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_preview_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_preview_done(self, _plan_path) -> None:
        self.status_label.setText("Pack preview ready.")

    def _on_export(self, force: bool) -> None:
        if self._pipeline is None:
            QMessageBox.warning(self, "No data", "Fetch orders first.")
            return

        if force:
            confirm = QMessageBox.question(
                self, "Force export?",
                "This exports every sheet regardless of how full it is, "
                "including under-filled ones. Vinyl on the unused area of "
                "those sheets is wasted.\n\nExport anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return

        self._set_busy(True)
        self._worker = _Worker(self._pipeline, "export", force=force)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_export_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _set_busy(self, busy: bool) -> None:
        for button in (self.fetch_btn, self.export_btn, self.force_btn):
            button.setEnabled(not busy)

    def _on_export_done(self, result) -> None:
        self._set_busy(False)
        lines = [
            f"Exported sheets: {result.exported_sheet_numbers or 'none'}",
            f"Held back orders: {len(result.held_back_orders)}",
        ]
        if result.oversize_orders:
            lines.append(
                f"OVERSIZE (cannot fit any sheet, needs attention): "
                f"{result.oversize_orders}"
            )
        if result.untagged_order_ids:
            lines.append(
                f"WARNING: {len(result.untagged_order_ids)} order(s) were "
                f"exported but NOT tagged in Shopify. They will be offered "
                f"for re-tagging on next startup."
            )
        else:
            lines.append(f"Tagged in Shopify: {len(result.tagged_order_ids)}")
        self.warnings_view.setPlainText("\n".join(lines))

    def _on_failed(self, message: str) -> None:
        self._set_busy(False)
        QMessageBox.critical(self, "Error", message)
