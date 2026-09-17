from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from core import paths as core_paths
from report import viewer as report_viewer


class HistoryPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "Production history is generated from sheets_report.csv — the "
            "workbook can stay open in Excel and this still works."
        ))

        open_btn = QPushButton("Open Report")
        open_btn.clicked.connect(self._open_report)
        layout.addWidget(open_btn)
        layout.addStretch(1)

    def _open_report(self) -> None:
        csv_path = core_paths.default_report_folder() / "sheets_report.csv"
        report_viewer.generate_report(csv_path=csv_path)
        report_viewer.open_report()
