from __future__ import annotations

from typing import List, Optional

from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QListWidget, QMessageBox,
    QVBoxLayout,
)

from core import settings as core_settings
from orchestrator.journal import Journal


class ReconciliationDialog(QDialog):
    def __init__(self, journals: List[Journal], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Unfinished run detected")
        self.setMinimumWidth(520)
        self._journals = journals

        layout = QVBoxLayout(self)

        total_untagged = sum(len(j.untagged_order_ids()) for j in journals)
        summary = QLabel(
            f"{len(journals)} run(s) did not finish cleanly.\n\n"
            f"{total_untagged} order(s) had sheets exported but were never "
            f"tagged in Shopify. Until they are tagged they will be fetched "
            f"again on the next run and cut a second time.\n\n"
            f"Tagging them now is safe — adding a tag that is already "
            f"present does nothing."
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        self.detail_list = QListWidget()
        for journal in journals:
            untagged = journal.untagged_order_ids()
            written = journal.written_sheet_numbers()
            self.detail_list.addItem(
                f"Run {journal.run_id} — sheets written: "
                f"{written or 'none'} — untagged orders: {len(untagged)}"
            )
            for order_id in untagged:
                self.detail_list.addItem(f"      order id {order_id}")
        layout.addWidget(self.detail_list)

        buttons = QDialogButtonBox()
        self.retry_button = buttons.addButton(
            "Tag them now", QDialogButtonBox.ButtonRole.AcceptRole
        )
        buttons.addButton("Dismiss", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self._retry_tagging)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _retry_tagging(self) -> None:
        from shopify.client import ShopifyClient, get_access_token
        from shopify.writeback import tag_orders

        cfg = core_settings.load()
        token: Optional[str] = None
        try:
            token = get_access_token()
        except Exception:
            token = None

        if not token or not cfg.get("shopify_domain"):
            QMessageBox.warning(
                self, "No credentials",
                "Shopify credentials are not configured, so tagging cannot "
                "be retried automatically. The affected order ids are listed "
                "above and can be tagged manually in the Shopify admin.",
            )
            return

        client = ShopifyClient(cfg["shopify_domain"], cfg.get("shopify_api_version", "2024-01"))
        tag = cfg.get("in_progress_tag", "in-progress")

        failures: List[str] = []
        for journal in self._journals:
            untagged = journal.untagged_order_ids()
            if not untagged:
                journal.record("export_complete")
                continue

            tag_orders(
                client, untagged, tag,
                on_each_success=lambda oid, j=journal: j.record("tag_ok", order_id=oid),
                on_each_failure=lambda oid, e: failures.append(oid),
            )
            if not journal.untagged_order_ids():
                journal.record("export_complete")

        if failures:
            QMessageBox.warning(
                self, "Partly tagged",
                f"{len(failures)} order(s) could not be tagged and will be "
                f"offered again next time the app starts.",
            )
        else:
            QMessageBox.information(
                self, "Done", "All outstanding orders are now tagged."
            )
        self.accept()
