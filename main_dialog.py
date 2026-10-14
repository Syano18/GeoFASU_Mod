# Developer: TechCraft by Chano
# email: c.dacpano@psa.gov.ph
# GeoFASU_Mod - Preprocessing and Postprocessing Dialogs

import os
from pathlib import Path

from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt, QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QDialog, QMessageBox, QWidget, QScrollArea, QFrame

try:
    from .style import apply_modern_style, setup_dialog_logo
    from .GeoFASU_dialog import GeoFASUDialog
    from .loader_dialog import LoaderDialog
    from .checker_dialog import CheckerDialog
    from .gpkg_to_excel_dialog import GpkgToExcelDialog
    from .updater import check_for_updates
except (ImportError, ValueError):
    from style import apply_modern_style, setup_dialog_logo
    from GeoFASU_dialog import GeoFASUDialog
    from loader_dialog import LoaderDialog
    from checker_dialog import CheckerDialog
    from gpkg_to_excel_dialog import GpkgToExcelDialog
    from updater import check_for_updates

FORM_CLASS, _ = uic.loadUiType(os.path.join(os.path.dirname(__file__), 'main_dialog.ui'))


def _make_scroll(widget):
    widget.setWindowFlags(Qt.Widget)
    widget.setMinimumSize(0, 0)
    if hasattr(widget, 'iconLabel'):
        widget.iconLabel.hide()
    if hasattr(widget, 'closeButton'):
        widget.closeButton.hide()
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setWidget(widget)
    return scroll


class PreprocessingDialog(QDialog, FORM_CLASS):
    """Preprocessing workflow dialog containing Excel to GPKG and Load/Generate QField."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.resize(560, 680)
        self.setMinimumSize(520, 640)
        self.setWindowTitle("GeoFASU_Mod - Preprocessing")
        apply_modern_style(self)
        setup_dialog_logo(self, max_width=220, max_height=80)

        icons_path = Path(__file__).parent / "icons"

        self.btn_update.setProperty("secondary", True)
        self.btn_close.setProperty("secondary", True)
        self.btn_update.clicked.connect(lambda: check_for_updates(self, silent_if_latest=False))
        self.btn_close.clicked.connect(self.close)

        # Modules
        self.tab_converter = GeoFASUDialog(parent=self)
        self.tab_loader = LoaderDialog(parent=self)

        self.tabs = [
            (self.tab_converter, "Excel to GPKG", "converter.png"),
            (self.tab_loader, "Load and Generate QField", "loader.png"),
        ]

        self.tabWidget.clear()
        for widget, title, icon_name in self.tabs:
            icon_file = icons_path / icon_name
            icon = QIcon(str(icon_file)) if icon_file.exists() else QIcon()
            self.tabWidget.addTab(_make_scroll(widget), icon, title)

    def set_active_tab(self, index: int):
        if 0 <= index < self.tabWidget.count():
            self.tabWidget.setCurrentIndex(index)


class PostprocessingDialog(QDialog, FORM_CLASS):
    """Postprocessing workflow dialog containing Quality Checker and GPKG to Excel."""
    def __init__(self, iface=None, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setupUi(self)
        self.resize(560, 680)
        self.setMinimumSize(520, 640)
        self.setWindowTitle("GeoFASU_Mod - Postprocessing")
        apply_modern_style(self)
        setup_dialog_logo(self, max_width=220, max_height=80)

        icons_path = Path(__file__).parent / "icons"

        self.btn_update.setProperty("secondary", True)
        self.btn_close.setProperty("secondary", True)
        self.btn_update.clicked.connect(lambda: check_for_updates(self, silent_if_latest=False))
        self.btn_close.clicked.connect(self.close)

        # Modules
        self.tab_checker = CheckerDialog(iface=self.iface, parent=self)
        self.tab_gpkg_excel = GpkgToExcelDialog(parent=self)

        self.tabs = [
            (self.tab_checker, "Quality Checker", "checker.png"),
            (self.tab_gpkg_excel, "GPKG to Excel", "gpkg_to_excel.png"),
        ]

        self.tabWidget.clear()
        for widget, title, icon_name in self.tabs:
            icon_file = icons_path / icon_name
            icon = QIcon(str(icon_file)) if icon_file.exists() else QIcon()
            self.tabWidget.addTab(_make_scroll(widget), icon, title)

        self.tabWidget.currentChanged.connect(self.on_tab_changed)

    def on_tab_changed(self, index):
        if index == 0:
            self.tab_checker.populate_layers()

    def set_active_tab(self, index: int):
        if 0 <= index < self.tabWidget.count():
            self.tabWidget.setCurrentIndex(index)
            if index == 0:
                self.tab_checker.populate_layers()


# Backward compatibility alias
GeoFASUMainDialog = PreprocessingDialog
