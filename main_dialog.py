# Developer: TechCraft by Chano
# email: c.dacpano@psa.gov.ph
# GeoFASU_Mod - Main Unified Dialog with Modular Tabs

import os
from pathlib import Path

from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt, QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QDialog, QMessageBox, QWidget

try:
    from .style import apply_modern_style, setup_dialog_logo
    from .GeoFASU_dialog import GeoFASUDialog
    from .loader_dialog import LoaderDialog
    from .qfield_dialog import QFieldDialog
    from .checker_dialog import CheckerDialog
    from .gpkg_to_excel_dialog import GpkgToExcelDialog
    from .updater import check_for_updates
except (ImportError, ValueError):
    from style import apply_modern_style, setup_dialog_logo
    from GeoFASU_dialog import GeoFASUDialog
    from loader_dialog import LoaderDialog
    from qfield_dialog import QFieldDialog
    from checker_dialog import CheckerDialog
    from gpkg_to_excel_dialog import GpkgToExcelDialog
    from updater import check_for_updates

FORM_CLASS, _ = uic.loadUiType(os.path.join(os.path.dirname(__file__), 'main_dialog.ui'))


class GeoFASUMainDialog(QDialog, FORM_CLASS):
    def __init__(self, iface=None, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setupUi(self)
        apply_modern_style(self)
        setup_dialog_logo(self, max_width=270, max_height=110)

        icons_path = Path(__file__).parent / "icons"

        self.btn_update.setProperty("secondary", True)
        self.btn_close.setProperty("secondary", True)
        self.btn_update.clicked.connect(lambda: check_for_updates(self, silent_if_latest=False))
        self.btn_close.clicked.connect(self.close)

        # Instantiate module tabs
        self.tab_converter = GeoFASUDialog(parent=self)
        self.tab_loader = LoaderDialog(parent=self)
        self.tab_qfield = QFieldDialog(parent=self)
        self.tab_checker = CheckerDialog(iface=self.iface, parent=self)
        self.tab_gpkg_excel = GpkgToExcelDialog(parent=self)

        self.tabs = [
            (self.tab_converter, "Excel to GPKG", "converter.png"),
            (self.tab_loader, "Load Layers", "loader.png"),
            (self.tab_qfield, "Style & QField", "qfield.png"),
            (self.tab_checker, "Quality Checker", "checker.png"),
            (self.tab_gpkg_excel, "GPKG to Excel", "gpkg_to_excel.png"),
        ]

        # Embed child widgets into tabWidget
        for widget, title, icon_name in self.tabs:
            widget.setWindowFlags(Qt.Widget)
            if hasattr(widget, 'iconLabel'):
                widget.iconLabel.hide()
            if hasattr(widget, 'closeButton'):
                widget.closeButton.hide()

            icon_file = icons_path / icon_name
            icon = QIcon(str(icon_file)) if icon_file.exists() else QIcon()
            self.tabWidget.addTab(widget, icon, title)

        # Tab switch signals
        self.tabWidget.currentChanged.connect(self.on_tab_changed)

        # Cross-module directory synchronization
        self._setup_dir_sync()

    def _setup_dir_sync(self):
        """Keep selected directories in sync between tabs for maximum user convenience."""
        def sync_from_loader():
            path = self.tab_loader.fileWidget.filePath()
            if path:
                if hasattr(self.tab_qfield, 'fileWidget') and self.tab_qfield.fileWidget.filePath() != path:
                    self.tab_qfield.fileWidget.setFilePath(path)
                if hasattr(self.tab_gpkg_excel, 'fileWidget') and self.tab_gpkg_excel.fileWidget.filePath() != path:
                    self.tab_gpkg_excel.fileWidget.setFilePath(path)

        def sync_from_qfield():
            path = self.tab_qfield.fileWidget.filePath()
            if path:
                if hasattr(self.tab_loader, 'fileWidget') and self.tab_loader.fileWidget.filePath() != path:
                    self.tab_loader.fileWidget.setFilePath(path)
                if hasattr(self.tab_gpkg_excel, 'fileWidget') and self.tab_gpkg_excel.fileWidget.filePath() != path:
                    self.tab_gpkg_excel.fileWidget.setFilePath(path)

        self.tab_loader.fileWidget.fileChanged.connect(sync_from_loader)
        self.tab_qfield.fileWidget.fileChanged.connect(sync_from_qfield)

    def on_tab_changed(self, index):
        """Trigger updates when switching between tabs."""
        current_widget = self.tabWidget.widget(index)
        if current_widget == self.tab_checker:
            self.tab_checker.populate_layers()

    def set_active_tab(self, index: int):
        """Switches the active tab by index."""
        if 0 <= index < self.tabWidget.count():
            self.tabWidget.setCurrentIndex(index)
