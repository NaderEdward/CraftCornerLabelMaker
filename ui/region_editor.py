from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
    QTextEdit, QVBoxLayout, QWidget,
)

from core import templates as core_templates
from regions import model as region_model
from regions import validate as region_validate


class RegionEditorTab(QWidget):
    def __init__(self) -> None:
        super().__init__()

        layout = QHBoxLayout(self)

        left = QVBoxLayout()
        left.addWidget(QLabel("Templates"))
        self.template_list = QListWidget()
        self.template_list.currentItemChanged.connect(self._on_select)
        left.addWidget(self.template_list)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.reload)
        left.addWidget(refresh_btn)

        layout.addLayout(left, 1)

        right = QVBoxLayout()
        right.addWidget(QLabel(
            "Region authoring is currently manual (§6.2): hand-edit the "
            "sidecar JSON in assets/Cut Zones and Templates/Regions/<template>.regions.json, then "
            "run:\n\n"
            "  python -m cli validate-regions --template <name> "
            "--render-preview out/\n\n"
            "to produce a crop-boundary preview per region before any "
            "production use. A drawing canvas is planned but not yet built."
        ))
        self.detail_view = QTextEdit()
        self.detail_view.setReadOnly(True)
        right.addWidget(self.detail_view, 1)

        layout.addLayout(right, 2)

        self.reload()

    def reload(self) -> None:
        self.template_list.clear()
        for name in core_templates.list_names():
            has_sidecar = region_model.sidecar_exists(name)
            item = QListWidgetItem(f"{'✓' if has_sidecar else '⚠'}  {name}")
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.template_list.addItem(item)

        orphans = region_model.list_orphaned_sidecars()
        if orphans:
            note = QListWidgetItem(f"⚠  {len(orphans)} orphaned sidecar(s) — see detail")
            note.setData(Qt.ItemDataRole.UserRole, None)
            self.template_list.addItem(note)

    def _on_select(self, current: QListWidgetItem, _previous) -> None:
        if current is None:
            return
        name = current.data(Qt.ItemDataRole.UserRole)
        if name is None:
            orphans = region_model.list_orphaned_sidecars()
            self.detail_view.setPlainText(
                "Orphaned sidecars (template no longer exists, never "
                "silently deleted per §6.2):\n\n" + "\n".join(orphans)
            )
            return

        lines = [f"Template: {name}"]
        problems = core_templates.validate(name)
        if problems:
            lines.append("\nTemplate problems:")
            lines.extend(f"  - {p}" for p in problems)

        if not region_model.sidecar_exists(name):
            lines.append(
                "\nNo region sidecar yet — this template is NOT "
                "production-ready (§6.2 point 4)."
            )
        else:
            rs = region_model.load(name)
            fp_ok = region_model.check_fingerprint(rs)
            lines.append(f"\nRegions ({len(rs.regions)}):")
            for r in rs.regions:
                lines.append(
                    f"  - {r.id}  \"{r.label}\"  rect=({r.rect.x},{r.rect.y},"
                    f"{r.rect.w},{r.rect.h})  sku_match={r.sku_match}  "
                    f"gap_mm={r.gap_mm}  allow_rotate={r.allow_rotate}"
                )
            region_problems = region_validate.validate_region_set(rs)
            if region_problems:
                lines.append("\nRegion problems:")
                lines.extend(f"  - {p}" for p in region_problems)
            if not fp_ok:
                lines.append(
                    "\n⚠ template_fingerprint mismatch — the template "
                    "artwork has changed since these regions were drawn. "
                    "Re-check them before producing (§6.2)."
                )

        self.detail_view.setPlainText("\n".join(lines))
