# Developer: TechCraft by Chano
# email: c.dacpano@psa.gov.ph

from pathlib import Path
from qgis.PyQt.QtWidgets import QAction, QMenu
from qgis.PyQt.QtGui import QIcon

from .main_dialog import GeoFASUMainDialog
from .updater import check_for_updates
from . import resources_rc


class GeoFASU:
    def __init__(self, iface):
        self.iface = iface
        self.actions = []
        self.main_dlg = None
        self.menu = None
        self.main_action = None

    def initGui(self):
        # Path to icons folder
        icons_path = Path(__file__).parent / "icons"

        # Create custom top-level menu
        self.menu = QMenu("&GeoFASU_Mod", self.iface.mainWindow())

        # Main Studio Action
        self.main_action = QAction(
            QIcon(str(icons_path / "icon.png")),
            "GeoFASU_Mod",
            self.iface.mainWindow()
        )
        self.main_action.triggered.connect(lambda: self.run_dialog(0))
        self.actions.append(self.main_action)

        # Tab shortcut actions
        self.folder_creator_action = QAction(
            QIcon(str(icons_path / "folder.png")),
            "Create Folder Structure",
            self.iface.mainWindow()
        )
        self.folder_creator_action.triggered.connect(lambda: self.run_dialog(0))

        self.converter_action = QAction(
            QIcon(str(icons_path / "converter.png")),
            "Convert Excel to GPKG",
            self.iface.mainWindow()
        )
        self.converter_action.triggered.connect(lambda: self.run_dialog(1))

        self.loader_action = QAction(
            QIcon(str(icons_path / "loader.png")),
            "Load Layers",
            self.iface.mainWindow()
        )
        self.loader_action.triggered.connect(lambda: self.run_dialog(2))

        self.qfield_action = QAction(
            QIcon(str(icons_path / "qfield.png")),
            "Apply Style & Generate QField",
            self.iface.mainWindow()
        )
        self.qfield_action.triggered.connect(lambda: self.run_dialog(3))

        self.checker_action = QAction(
            QIcon(str(icons_path / "checker.png")),
            "Data Quality Checker",
            self.iface.mainWindow()
        )
        self.checker_action.triggered.connect(lambda: self.run_dialog(4))

        self.gpkg_to_excel_action = QAction(
            QIcon(str(icons_path / "gpkg_to_excel.png")),
            "Convert GPKG to Excel",
            self.iface.mainWindow()
        )
        self.gpkg_to_excel_action.triggered.connect(lambda: self.run_dialog(5))

        self.update_action = QAction(
            QIcon(str(icons_path / "update.png")),
            "Check for Updates...",
            self.iface.mainWindow()
        )
        self.update_action.triggered.connect(
            lambda: check_for_updates(self.iface.mainWindow(), silent_if_latest=False)
        )

        # Populate menu
        self.menu.addAction(self.main_action)
        self.menu.addSeparator()
        self.menu.addAction(self.folder_creator_action)
        self.menu.addAction(self.converter_action)
        self.menu.addAction(self.loader_action)
        self.menu.addAction(self.qfield_action)
        self.menu.addAction(self.checker_action)
        self.menu.addAction(self.gpkg_to_excel_action)
        self.menu.addSeparator()
        self.menu.addAction(self.update_action)

        # Add toolbar icon
        if hasattr(self.iface, 'addToolBarIcon'):
            self.iface.addToolBarIcon(self.main_action)

        # Add custom menu directly to QGIS top-level menu bar
        menu_bar = self.iface.mainWindow().menuBar()
        help_menu = self.iface.helpMenu() if hasattr(self.iface, 'helpMenu') else None
        if help_menu:
            menu_bar.insertMenu(help_menu.menuAction(), self.menu)
        else:
            menu_bar.addMenu(self.menu)

    def unload(self):
        # Remove toolbar icon
        if hasattr(self.iface, 'removeToolBarIcon') and self.main_action:
            self.iface.removeToolBarIcon(self.main_action)

        # Remove the top-level menu from the QGIS main window menu bar
        if self.menu:
            menu_bar = self.iface.mainWindow().menuBar()
            menu_bar.removeAction(self.menu.menuAction())
            self.menu.deleteLater()
            self.menu = None

    def run_dialog(self, tab_index=0):
        if not self.main_dlg:
            self.main_dlg = GeoFASUMainDialog(self.iface)

        self.main_dlg.set_active_tab(tab_index)
        self.main_dlg.show()
        self.main_dlg.raise_()
        self.main_dlg.activateWindow()

    # Backward compatibility helpers
    def run_folder_creator(self):
        self.run_dialog(0)

    def run_converter(self):
        self.run_dialog(1)

    def run_loader(self):
        self.run_dialog(2)

    def run_qfield(self):
        self.run_dialog(3)

    def run_checker(self):
        self.run_dialog(4)

    def run_gpkg_to_excel(self):
        self.run_dialog(5)
