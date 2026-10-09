#Author: Mapping_Kalinga
#email: c.dacpano@psa.gov.ph

from qgis.PyQt.QtWidgets import QAction, QMenu
from qgis.PyQt.QtGui import QIcon
from pathlib import Path
from .GeoFASU_dialog import GeoFASUDialog          # Converter UI
from .gpkg_to_excel_dialog import GpkgToExcelDialog
from .loader_dialog import LoaderDialog  # Loader UI (assumed)
from .updater import check_for_updates
from . import resources_rc

class GeoFASU:
    def __init__(self, iface):
        self.iface = iface
        self.actions = []
        self.converter_dlg = None
        self.loader_dlg = None
        self.update_action = None

    def initGui(self):
        # Path to icons folder
        icons_path = Path(__file__).parent / "icons"

        # Create custom top-level menu
        self.menu = QMenu("&GeoFASU_Mod", self.iface.mainWindow())

        # Create sub actions
        self.converter_action = QAction(
            QIcon(str(icons_path / "converter.png")),
            "Convert excel to gpkg",
            self.iface.mainWindow()
        )
        self.converter_action.triggered.connect(self.run_converter)

        self.gpkg_to_excel_action = QAction(
            QIcon(str(icons_path / "converter.png")),
            "Convert geopackage to excel",
            self.iface.mainWindow()
        )
        self.gpkg_to_excel_action.triggered.connect(self.run_gpkg_to_excel)

        self.loader_action = QAction(
            QIcon(str(icons_path / "loader.png")),
            "Load and Generate Qfield",
            self.iface.mainWindow()
        )
        self.loader_action.triggered.connect(self.run_loader)

        self.update_action = QAction(
            QIcon(str(icons_path / "icon.png")),
            "Check for Updates...",
            self.iface.mainWindow()
        )
        self.update_action.triggered.connect(lambda: check_for_updates(self.iface.mainWindow(), silent_if_latest=False))

        # Add actions into the custom menu
        self.menu.addAction(self.converter_action)
        self.menu.addAction(self.loader_action)
        self.menu.addAction(self.gpkg_to_excel_action)
        self.menu.addSeparator()
        self.menu.addAction(self.update_action)

        # Add custom menu directly to QGIS top-level menu bar
        menu_bar = self.iface.mainWindow().menuBar()
        help_menu = self.iface.helpMenu() if hasattr(self.iface, 'helpMenu') else None
        if help_menu:
            menu_bar.insertMenu(help_menu.menuAction(), self.menu)
        else:
            menu_bar.addMenu(self.menu)

    def unload(self):
        # Remove the top-level menu from the QGIS main window menu bar
        if self.menu:
            menu_bar = self.iface.mainWindow().menuBar()
            menu_bar.removeAction(self.menu.menuAction())
            self.menu.deleteLater()
            self.menu = None
            
    def run_converter(self):
        if not self.converter_dlg:
            self.converter_dlg = GeoFASUDialog()
        self.converter_dlg.show()
        self.converter_dlg.exec_()

    def run_gpkg_to_excel(self):
        if not hasattr(self, 'gpkg_to_excel_dlg') or not self.gpkg_to_excel_dlg:
            self.gpkg_to_excel_dlg = GpkgToExcelDialog()
        self.gpkg_to_excel_dlg.show()
        self.gpkg_to_excel_dlg.exec_()

    def run_loader(self):
        if not self.loader_dlg:
            self.loader_dlg = LoaderDialog()
        self.loader_dlg.show()
        self.loader_dlg.exec_()
