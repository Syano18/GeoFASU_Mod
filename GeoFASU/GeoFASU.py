#Author: Mapping_Kalinga
#email: c.dacpano@psa.gov.ph

from qgis.PyQt.QtWidgets import QAction, QMenu
from qgis.PyQt.QtGui import QIcon
from pathlib import Path
from .GeoFASU_dialog import GeoFASUDialog          # Converter UI
from .gpkg_to_excel_dialog import GpkgToExcelDialog
from .loader_dialog import LoaderDialog  # Loader UI (assumed)
from . import resources_rc

class GeoFASU:
    def __init__(self, iface):
        self.iface = iface
        self.actions = []
        self.converter_dlg = None
        self.loader_dlg = None

    def initGui(self):
        # Path to icons folder
        icons_path = Path(__file__).parent / "icons"

        # Create custom menu with icon
        self.menu = QMenu("GeoFASU Ori", self.iface.mainWindow())
        self.menu.setIcon(QIcon(str(icons_path / "icon.png")))

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

        # Add actions into the custom menu
        self.menu.addAction(self.converter_action)
        self.menu.addAction(self.loader_action)
        self.menu.addAction(self.gpkg_to_excel_action)

        # Finally add your custom menu into QGIS Plugins menu bar
        self.iface.pluginMenu().addMenu(self.menu)

    def unload(self):
        # Remove the actions from the menu bar
        if self.converter_action:
            self.iface.removePluginMenu("GeoFASU Ori", self.converter_action)
            self.iface.removeToolBarIcon(self.converter_action)

        if hasattr(self, 'gpkg_to_excel_action') and self.gpkg_to_excel_action:
            self.iface.removePluginMenu("GeoFASU Ori", self.gpkg_to_excel_action)
            self.iface.removeToolBarIcon(self.gpkg_to_excel_action)

        if self.loader_action:
            self.iface.removePluginMenu("GeoFASU Ori", self.loader_action)
            self.iface.removeToolBarIcon(self.loader_action)

        # Remove the whole GeoFASU menu
        if self.menu:
            self.iface.pluginMenu().removeAction(self.menu.menuAction())
            
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
