# Developer: TechCraft by Chano
# email: c.dacpano@psa.gov.ph

from pathlib import Path
from qgis.PyQt.QtWidgets import QAction, QMenu
from qgis.PyQt.QtGui import QIcon

try:
    from .main_dialog import GeoFASUMainDialog
    from .folder_creator_dialog import FolderCreatorDialog
    from .updater import check_for_updates
    from . import resources_rc
except (ImportError, ValueError):
    from main_dialog import GeoFASUMainDialog
    from folder_creator_dialog import FolderCreatorDialog
    from updater import check_for_updates
    import resources_rc


class GeoFASU:
    def __init__(self, iface):
        self.iface = iface
        self.actions = []
        self.main_dlg = None
        self.folder_creator_dlg = None
        self.menu = None
        self.main_action = None

    def initGui(self):
        # Path to icons folder
        icons_path = Path(__file__).parent / "icons"

        # Create custom top-level menu
        self.menu = QMenu("&GeoFASU_Mod", self.iface.mainWindow())

        # Standalone Folder Creator Action
        self.folder_creator_action = QAction(
            QIcon(str(icons_path / "folder.png")),
            "Create Folder Structure",
            self.iface.mainWindow()
        )
        self.folder_creator_action.triggered.connect(self.run_folder_creator)

        # Main Studio Action (Opens tabbed dialog)
        self.main_action = QAction(
            QIcon(str(icons_path / "icon.png")),
            "GeoFASU_Mod Studio",
            self.iface.mainWindow()
        )
        self.main_action.triggered.connect(lambda: self.run_dialog(0))
        self.actions.append(self.main_action)

        self.update_action = QAction(
            QIcon(str(icons_path / "update.png")),
            "Check for Updates...",
            self.iface.mainWindow()
        )
        self.update_action.triggered.connect(
            lambda: check_for_updates(self.iface.mainWindow(), silent_if_latest=False)
        )

        # Populate menu (clean layout without redundant sub-items)
        self.menu.addAction(self.folder_creator_action)
        self.menu.addSeparator()
        self.menu.addAction(self.main_action)
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

    def run_folder_creator(self):
        if not self.folder_creator_dlg:
            self.folder_creator_dlg = FolderCreatorDialog()
        self.folder_creator_dlg.show()
        self.folder_creator_dlg.raise_()
        self.folder_creator_dlg.activateWindow()

    def run_dialog(self, module_target=0):
        if not self.main_dlg:
            self.main_dlg = GeoFASUMainDialog(self.iface)

        self.main_dlg.set_active_module(module_target)
        self.main_dlg.show()
        self.main_dlg.raise_()
        self.main_dlg.activateWindow()

    # Backward compatibility helpers
    def run_converter(self):
        self.run_dialog('converter')

    def run_loader(self):
        self.run_dialog('loader')

    def run_qfield(self):
        self.run_dialog('qfield')

    def run_checker(self):
        self.run_dialog('checker')

    def run_gpkg_to_excel(self):
        self.run_dialog('gpkg_to_excel')
