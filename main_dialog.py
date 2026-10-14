# Developer: TechCraft by Chano
# email: c.dacpano@psa.gov.ph
# GeoFASU_Mod - Main Unified Dialog with Preprocessing and Postprocessing Groups

import os
from pathlib import Path

from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt, QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QDialog, QMessageBox, QWidget, QScrollArea, QFrame, QTabWidget

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


class GeoFASUMainDialog(QDialog, FORM_CLASS):
    def __init__(self, iface=None, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setupUi(self)
        apply_modern_style(self)
        setup_dialog_logo(self, max_width=220, max_height=80)

        icons_path = Path(__file__).parent / "icons"

        self.btn_update.setProperty("secondary", True)
        self.btn_close.setProperty("secondary", True)
        self.btn_update.clicked.connect(lambda: check_for_updates(self, silent_if_latest=False))
        self.btn_close.clicked.connect(self.close)

        # Module instances
        self.tab_converter = GeoFASUDialog(parent=self)
        self.tab_loader = LoaderDialog(parent=self)
        self.tab_checker = CheckerDialog(iface=self.iface, parent=self)
        self.tab_gpkg_excel = GpkgToExcelDialog(parent=self)

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
            scroll.setWidget(widget)
            return scroll

        # --- Group 1: Preprocessing ---
        self.sub_tab_pre = QTabWidget()
        self.sub_tab_pre.setObjectName("subTabWidget")
        self.sub_tab_pre.setProperty("class", "subTabWidget")

        pre_modules = [
            (self.tab_converter, "Excel to GPKG", "converter.png"),
            (self.tab_loader, "Load and Generate QField", "loader.png"),
        ]
        for w, title, icon_name in pre_modules:
            icon_file = icons_path / icon_name
            icon = QIcon(str(icon_file)) if icon_file.exists() else QIcon()
            self.sub_tab_pre.addTab(_make_scroll(w), icon, title)

        # --- Group 2: Postprocessing ---
        self.sub_tab_post = QTabWidget()
        self.sub_tab_post.setObjectName("subTabWidget")
        self.sub_tab_post.setProperty("class", "subTabWidget")

        post_modules = [
            (self.tab_checker, "Quality Checker", "checker.png"),
            (self.tab_gpkg_excel, "GPKG to Excel", "gpkg_to_excel.png"),
        ]
        for w, title, icon_name in post_modules:
            icon_file = icons_path / icon_name
            icon = QIcon(str(icon_file)) if icon_file.exists() else QIcon()
            self.sub_tab_post.addTab(_make_scroll(w), icon, title)

        # Add groups to main tabWidget
        icon_pre = QIcon(str(icons_path / "converter.png")) if (icons_path / "converter.png").exists() else QIcon()
        icon_post = QIcon(str(icons_path / "checker.png")) if (icons_path / "checker.png").exists() else QIcon()

        self.tabWidget.clear()
        self.tabWidget.addTab(self.sub_tab_pre, icon_pre, "Preprocessing")
        self.tabWidget.addTab(self.sub_tab_post, icon_post, "Postprocessing")

        # Tab switch signals
        self.tabWidget.currentChanged.connect(self.on_main_tab_changed)
        self.sub_tab_post.currentChanged.connect(self.on_post_sub_tab_changed)

        # Cross-module directory synchronization
        self._setup_dir_sync()

    def _setup_dir_sync(self):
        """Keep selected directories in sync between tabs for maximum user convenience."""
        def sync_from_loader():
            path = self.tab_loader.fileWidget.filePath()
            if path:
                if hasattr(self.tab_gpkg_excel, 'fileWidget') and self.tab_gpkg_excel.fileWidget.filePath() != path:
                    self.tab_gpkg_excel.fileWidget.setFilePath(path)

        def sync_from_gpkg_excel():
            path = self.tab_gpkg_excel.fileWidget.filePath()
            if path:
                if hasattr(self.tab_loader, 'fileWidget') and self.tab_loader.fileWidget.filePath() != path:
                    self.tab_loader.fileWidget.setFilePath(path)

        self.tab_loader.fileWidget.fileChanged.connect(sync_from_loader)
        self.tab_gpkg_excel.fileWidget.fileChanged.connect(sync_from_gpkg_excel)

    def on_main_tab_changed(self, index):
        """Called when switching between Preprocessing and Postprocessing."""
        if index == 1 and self.sub_tab_post.currentIndex() == 0:
            self.tab_checker.populate_layers()

    def on_post_sub_tab_changed(self, index):
        """Called when switching within Postprocessing sub-tabs."""
        if index == 0:
            self.tab_checker.populate_layers()

    def set_active_module(self, target):
        """
        Switches directly to a specific workflow module:
        0 or 'converter'      -> Preprocessing > Excel to GPKG
        1 or 'loader'/'qfield'-> Preprocessing > Load and Generate QField
        2 or 'checker'        -> Postprocessing > Quality Checker
        3 or 'gpkg_to_excel'  -> Postprocessing > GPKG to Excel
        """
        mapping = {
            0: (0, 0),
            'converter': (0, 0),
            'excel_to_gpkg': (0, 0),
            1: (0, 1),
            'loader': (0, 1),
            'load_layers': (0, 1),
            'qfield': (0, 1),
            'generate_qfield': (0, 1),
            2: (1, 0),
            'checker': (1, 0),
            'quality_checker': (1, 0),
            3: (1, 1),
            4: (1, 1),
            'gpkg_to_excel': (1, 1),
        }
        main_idx, sub_idx = mapping.get(target, (0, 0))
        self.tabWidget.setCurrentIndex(main_idx)
        if main_idx == 0:
            self.sub_tab_pre.setCurrentIndex(sub_idx)
        else:
            self.sub_tab_post.setCurrentIndex(sub_idx)

    def set_active_tab(self, index: int):
        """Backward compatibility helper."""
        self.set_active_module(index)
