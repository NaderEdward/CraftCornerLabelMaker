from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox,
    QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from core import settings as core_settings


class SheetConfigPanel(QWidget):

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)

        sheet_box = QGroupBox("Regular Sheet  (large-format vinyl)")
        form = QFormLayout(sheet_box)

        self.width_mm = QDoubleSpinBox()
        self.width_mm.setRange(10, 5000)
        self.width_mm.setSuffix(" mm")
        self.height_mm = QDoubleSpinBox()
        self.height_mm.setRange(10, 5000)
        self.height_mm.setSuffix(" mm")
        self.dpi = QComboBox()
        self.dpi.addItems(["72", "96", "150", "300"])
        self.gap_mm = QDoubleSpinBox()
        self.gap_mm.setRange(0, 50)
        self.gap_mm.setSuffix(" mm")
        self.threshold_pct = QSpinBox()
        self.threshold_pct.setRange(1, 100)
        self.threshold_pct.setSuffix(" %")
        self.strategy = QComboBox()
        self.strategy.addItems(["space_optimizer", "maxrects", "shelf", "grid"])
        self.label_tiles = QCheckBox("Draw order-number labels on sheet (opt-in)")

        form.addRow("Width", self.width_mm)
        form.addRow("Height", self.height_mm)
        form.addRow("DPI", self.dpi)
        form.addRow("Inter-tile gap", self.gap_mm)
        form.addRow("Fill threshold", self.threshold_pct)
        form.addRow("Pack strategy", self.strategy)
        form.addRow("", self.label_tiles)
        layout.addWidget(sheet_box)

        ionon_box = QGroupBox("Iron-On Sheet  (letter-size, separate vinyl)")
        iform = QFormLayout(ionon_box)

        self.ironon_width_mm = QDoubleSpinBox()
        self.ironon_width_mm.setRange(10, 1000)
        self.ironon_width_mm.setSuffix(" mm")
        self.ironon_height_mm = QDoubleSpinBox()
        self.ironon_height_mm.setRange(10, 1000)
        self.ironon_height_mm.setSuffix(" mm")
        self.ironon_dpi = QComboBox()
        self.ironon_dpi.addItems(["150", "300", "600"])

        iform.addRow("Width", self.ironon_width_mm)
        iform.addRow("Height", self.ironon_height_mm)
        iform.addRow("DPI", self.ironon_dpi)
        layout.addWidget(ionon_box)

        shopify_box = QGroupBox("Shopify")
        sform = QFormLayout(shopify_box)

        self.shop_domain  = QLineEdit()
        self.shop_domain.setPlaceholderText("thecraftcorner-eg.myshopify.com")
        self.api_version  = QLineEdit()
        self.api_version.setPlaceholderText("2025-04")

        self.client_id     = QLineEdit()
        self.client_id.setPlaceholderText("From Dev Dashboard → API credentials")
        self.client_secret = QLineEdit()
        self.client_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.client_secret.setPlaceholderText("From Dev Dashboard → API credentials")

        self.static_token = QLineEdit()
        self.static_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.static_token.setPlaceholderText("shpat_... (only if you have a pre-2026 legacy app)")

        self.test_btn = QPushButton("Test Connection")
        test_btn = self.test_btn
        test_btn.clicked.connect(self._test_connection)

        sform.addRow("Shop domain",   self.shop_domain)
        sform.addRow("API version",   self.api_version)
        sform.addRow("Client ID",     self.client_id)
        sform.addRow("Client Secret", self.client_secret)
        sform.addRow("Static token (legacy)", self.static_token)
        sform.addRow("", test_btn)
        layout.addWidget(shopify_box)

        out_box = QGroupBox("Output")
        oform = QFormLayout(out_box)
        self.output_folder = QLineEdit()
        oform.addRow("Sheets folder", self.output_folder)
        layout.addWidget(out_box)


        num_box = QGroupBox("Sheet Numbering")
        nform = QFormLayout(num_box)
        self.sheet_number_reset = QSpinBox()
        self.sheet_number_reset.setRange(0, 99999)
        self.sheet_number_reset.setSpecialValueText("(current)")
        self.sheet_number_reset.setToolTip(
            "Set to 0 to restart from sheet #001 on the next export. "
            "Any other value sets the high-water mark: the next sheet "
            "will be this number + 1."
        )
        reset_btn = QPushButton("Apply Reset")
        reset_btn.clicked.connect(self._reset_sheet_number)
        nform.addRow("Reset counter to", self.sheet_number_reset)
        nform.addRow("", reset_btn)
        layout.addWidget(num_box)

        save_btn = QPushButton("Save Settings")
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)
        layout.addStretch(1)

        self._load()

    def _load(self) -> None:
        cfg = core_settings.load()
        self.width_mm.setValue(cfg["sheet_width_mm"])
        self.height_mm.setValue(cfg["sheet_height_mm"])
        self.dpi.setCurrentText(str(cfg["sheet_dpi"]))
        self.gap_mm.setValue(cfg["inter_tile_gap_mm"])
        self.threshold_pct.setValue(int(round(cfg["fill_threshold"] * 100)))
        self.strategy.setCurrentText(cfg["pack_strategy"])
        self.label_tiles.setChecked(cfg["label_tiles"])
        self.ironon_width_mm.setValue(cfg.get("ironon_sheet_width_mm", 215.9))
        self.ironon_height_mm.setValue(cfg.get("ironon_sheet_height_mm", 279.4))
        self.ironon_dpi.setCurrentText(str(cfg.get("ironon_sheet_dpi", 300)))
        self.shop_domain.setText(cfg["shopify_domain"])
        self.api_version.setText(cfg["shopify_api_version"])
        self.output_folder.setText(cfg["output_folder"])

        try:
            from shopify.client import get_client_credentials, get_static_token
            cid, sec = get_client_credentials()
            if cid:
                self.client_id.setText(cid)
            if sec:
                self.client_secret.setText("••••••••")
            token = get_static_token()
            if token:
                self.static_token.setText("••••••••")
        except Exception:
            pass

    def _save(self) -> None:
        cfg = core_settings.load()
        cfg["sheet_width_mm"] = self.width_mm.value()
        cfg["sheet_height_mm"] = self.height_mm.value()
        cfg["sheet_dpi"] = int(self.dpi.currentText())
        cfg["inter_tile_gap_mm"] = self.gap_mm.value()
        cfg["fill_threshold"] = self.threshold_pct.value() / 100.0
        cfg["pack_strategy"] = self.strategy.currentText()
        cfg["label_tiles"] = self.label_tiles.isChecked()
        cfg["ironon_sheet_width_mm"] = self.ironon_width_mm.value()
        cfg["ironon_sheet_height_mm"] = self.ironon_height_mm.value()
        cfg["ironon_sheet_dpi"] = int(self.ironon_dpi.currentText())
        cfg["shopify_domain"] = self.shop_domain.text().strip()
        cfg["shopify_api_version"] = self.api_version.text().strip()
        cfg["output_folder"] = self.output_folder.text().strip()
        core_settings.save(cfg)

        try:
            from shopify.client import (store_client_credentials,
                                        store_static_token)
            cid = self.client_id.text().strip()
            sec = self.client_secret.text().strip()
            if cid and "•" not in cid:
                store_client_credentials(
                    cid, sec if ("•" not in sec and sec) else ""
                )
            elif sec and "•" not in sec:
                store_client_credentials("", sec)

            tok = self.static_token.text().strip()
            if tok and "•" not in tok:
                store_static_token(tok)
        except Exception:
            pass


    def _reset_sheet_number(self) -> None:
        from PyQt6.QtWidgets import QMessageBox
        new_val = self.sheet_number_reset.value()
        next_n = new_val + 1
        reply = QMessageBox.question(
            self, "Reset sheet counter",
            f"Set last sheet number to {new_val}?\n"
            f"The next export will start at sheet #{next_n:03d}.\n\n"
            f"This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        cfg = core_settings.load()
        cfg["last_sheet_number"] = new_val
        core_settings.save(cfg)
        self.sheet_number_reset.setValue(0)
        QMessageBox.information(
            self, "Done",
            f"Sheet counter reset. Next sheet will be #{next_n:03d}."
        )

    def _test_connection(self) -> None:
        from PyQt6.QtWidgets import QMessageBox
        from shopify.client import ShopifyClient, credentials_configured

        domain  = self.shop_domain.text().strip()
        version = self.api_version.text().strip() or "2025-04"

        if not domain:
            QMessageBox.warning(self, "Missing field",
                                "Enter the shop domain first.")
            return
        if not credentials_configured():
            QMessageBox.warning(self, "No credentials",
                                "Enter Client ID + Client Secret "
                                "(or a legacy static token) and click "
                                "Save Settings first.")
            return

        self.test_btn.setEnabled(False)
        self.test_btn.setText("Testing…")

        try:
            client = ShopifyClient(domain, version)
            ok, message = client.test_connection()
        except Exception as e:
            ok, message = False, str(e)
        finally:
            self.test_btn.setEnabled(True)
            self.test_btn.setText("Test Connection")

        if ok:
            QMessageBox.information(self, "Connected ✓", message)
        else:
            QMessageBox.critical(self, "Connection failed", message)
