from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QVBoxLayout,
)

from core import settings as core_settings


class ShopifyCredentialsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Shopify Credentials")

        layout = QVBoxLayout(self)
        form = QFormLayout()

        cfg = core_settings.load()
        self.shop_domain = QLineEdit(cfg.get("shopify_domain", ""))
        self.access_token = QLineEdit()
        self.access_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.access_token.setPlaceholderText("Leave blank to keep the current token")

        form.addRow("Shop domain", self.shop_domain)
        form.addRow("Access token", self.access_token)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self) -> None:
        cfg = core_settings.load()
        cfg["shopify_domain"] = self.shop_domain.text().strip()
        core_settings.save(cfg)

        token = self.access_token.text().strip()
        if token:
            try:
                from shopify.client import store_access_token
                store_access_token(token)
            except Exception:
                pass
        super().accept()
