# Developer: TechCraft by Chano
# email: c.dacpano@psa.gov.ph
# GeoFASU_Mod - Postprocessing From Tablet Loader Module

import os
from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt, QCoreApplication, pyqtSignal
from qgis.PyQt.QtWidgets import QDialog
from qgis.core import QgsProject, QgsVectorLayer, QgsProviderRegistry

try:
    from .style import apply_modern_style, setup_dialog_logo
except (ImportError, ValueError):
    from style import apply_modern_style, setup_dialog_logo

FORM_CLASS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "post_loader_dialog.ui")
)

DEFAULT_DIR = r"C:\PSA-GIS\GeoFASU\Kalinga\Project files"


def list_subfolders(folder_path: str):
    """Returns a sorted list of subdirectory names inside folder_path."""
    if not folder_path or not os.path.isdir(folder_path):
        return []
    try:
        return sorted(
            d
            for d in os.listdir(folder_path)
            if os.path.isdir(os.path.join(folder_path, d))
        )
    except OSError:
        return []


class PostLoaderDialog(QDialog, FORM_CLASS):
    """Postprocessing Loader tab for browsing and loading From Tablet folders."""

    project_loaded = pyqtSignal()

    def __init__(self, iface=None, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setupUi(self)
        apply_modern_style(self)
        if hasattr(self, "iconLabel"):
            setup_dialog_logo(self)

        self.progressBar.setValue(0)
        self.loadButton.setEnabled(False)

        self.comboxFolder1.setPlaceholderText("-- Select Survey Folder --")
        self.comboxFolder2.setPlaceholderText("-- Select City/Municipality Folder --")
        self.comboxFolder3.setPlaceholderText("-- Select Tablet Project Folder --")

        # Signals
        self.fileWidget.fileChanged.connect(self.populate_folder1)
        self.comboxFolder1.currentIndexChanged.connect(self.on_folder1_changed)
        self.comboxFolder2.currentIndexChanged.connect(self.on_folder2_changed)
        self.comboxFolder3.currentIndexChanged.connect(self.on_folder3_changed)
        self.loadButton.clicked.connect(self.load_selected_folder)

        # Initialize with default directory
        self.fileWidget.setFilePath(DEFAULT_DIR)
        self.populate_folder1()

    def log(self, message: str, level: str = "INFO"):
        """Appends a line of text to the logs widget with level indicator."""
        prefix = {
            "INFO": "",
            "SUCCESS": "✓ ",
            "WARNING": "⚠ ",
            "ERROR": "✗ ",
        }.get(level.upper(), "")
        if hasattr(self, "logsTextEdit") and self.logsTextEdit:
            self.logsTextEdit.appendPlainText(f"{prefix}{message}")
            self.logsTextEdit.verticalScrollBar().setValue(
                self.logsTextEdit.verticalScrollBar().maximum()
            )

    def _from_tablet_dir(self) -> str:
        base_dir = self.fileWidget.filePath().strip() if hasattr(self, "fileWidget") else ""
        if not base_dir:
            base_dir = DEFAULT_DIR
        return os.path.join(base_dir, "From Tablet")

    def populate_folder1(self):
        """Populates dropdown 1 with folders inside <default directory>/From Tablet."""
        self.comboxFolder1.blockSignals(True)
        self.comboxFolder2.blockSignals(True)
        self.comboxFolder3.blockSignals(True)

        self.comboxFolder1.clear()
        self.comboxFolder2.clear()
        self.comboxFolder3.clear()
        self.loadButton.setEnabled(False)

        folders = list_subfolders(self._from_tablet_dir())
        if folders:
            self.comboxFolder1.addItems(folders)
        self.comboxFolder1.setCurrentIndex(-1)
        self.comboxFolder2.setCurrentIndex(-1)
        self.comboxFolder3.setCurrentIndex(-1)

        self.comboxFolder1.blockSignals(False)
        self.comboxFolder2.blockSignals(False)
        self.comboxFolder3.blockSignals(False)

    def on_folder1_changed(self):
        """Populates dropdown 2 with folders inside the selected folder from dropdown 1."""
        self.comboxFolder2.blockSignals(True)
        self.comboxFolder3.blockSignals(True)

        self.comboxFolder2.clear()
        self.comboxFolder3.clear()
        self.loadButton.setEnabled(False)

        sel1 = self.comboxFolder1.currentText().strip()
        if sel1:
            target = os.path.join(self._from_tablet_dir(), sel1)
            folders = list_subfolders(target)
            if folders:
                self.comboxFolder2.addItems(folders)
        self.comboxFolder2.setCurrentIndex(-1)
        self.comboxFolder3.setCurrentIndex(-1)

        self.comboxFolder2.blockSignals(False)
        self.comboxFolder3.blockSignals(False)

    def on_folder2_changed(self):
        """Populates dropdown 3 with folders inside the selected folder from dropdown 2."""
        self.comboxFolder3.blockSignals(True)

        self.comboxFolder3.clear()
        self.loadButton.setEnabled(False)

        sel1 = self.comboxFolder1.currentText().strip()
        sel2 = self.comboxFolder2.currentText().strip()
        if sel1 and sel2:
            target = os.path.join(self._from_tablet_dir(), sel1, sel2)
            folders = list_subfolders(target)
            if folders:
                self.comboxFolder3.addItems(folders)
        self.comboxFolder3.setCurrentIndex(-1)

        self.comboxFolder3.blockSignals(False)

    def on_folder3_changed(self):
        """Updates Load button state when a folder is selected in dropdown 3."""
        sel3 = self.comboxFolder3.currentText().strip()
        self.loadButton.setEnabled(bool(sel3))

    def get_selected_folder_path(self) -> str:
        """Returns the full directory path resolved from all 3 dropdown selections."""
        sel1 = self.comboxFolder1.currentText().strip()
        sel2 = self.comboxFolder2.currentText().strip()
        sel3 = self.comboxFolder3.currentText().strip()
        if not (sel1 and sel2 and sel3):
            return ""
        return os.path.join(self._from_tablet_dir(), sel1, sel2, sel3)

    def load_selected_folder(self):
        """Loads the QGIS project (.qgz/.qgs) or GeoPackage layers from the selected folder."""
        folder_path = self.get_selected_folder_path()
        if not folder_path or not os.path.isdir(folder_path):
            self.log("Please select valid folders across all three dropdowns.", "WARNING")
            return

        self.logsTextEdit.clear()
        self.progressBar.setValue(10)
        self.loadButton.setEnabled(False)
        QCoreApplication.processEvents()

        try:
            entries = sorted(os.listdir(folder_path))
            project_files = [
                os.path.join(folder_path, f)
                for f in entries
                if f.lower().endswith((".qgz", ".qgs"))
            ]

            if project_files:
                proj_path = project_files[0]
                self.log(f"Loading QGIS project:\n  {proj_path}", "INFO")
                self.progressBar.setValue(40)
                QCoreApplication.processEvents()

                project = QgsProject.instance()
                project.clear()
                ok = project.read(proj_path)
                if not ok:
                    self.log(f"Failed to read project file: {proj_path}", "ERROR")
                    self.progressBar.setValue(0)
                    return

                if self.iface and hasattr(self.iface, "mapCanvas") and self.iface.mapCanvas():
                    self.iface.mapCanvas().refresh()

                self.progressBar.setValue(100)
                self.log(f"Loaded project '{os.path.basename(proj_path)}' successfully.", "SUCCESS")
                self.project_loaded.emit()
                return

            gpkg_files = [
                os.path.join(folder_path, f)
                for f in entries
                if f.lower().endswith(".gpkg")
            ]
            if not gpkg_files:
                self.log(f"No .qgz/.qgs project or .gpkg files found in:\n  {folder_path}", "WARNING")
                self.progressBar.setValue(0)
                return

            loaded_count = 0
            project = QgsProject.instance()
            total = len(gpkg_files)
            for idx, gpkg_path in enumerate(gpkg_files):
                sublayers = (
                    QgsProviderRegistry.instance()
                    .providerMetadata("ogr")
                    .querySublayers(gpkg_path)
                )
                for sub in sublayers:
                    if sub.name().lower() in ("layer_styles", "sqlite_sequence"):
                        continue
                    display_name = (
                        os.path.splitext(os.path.basename(gpkg_path))[0]
                        if len(sublayers) == 1
                        else sub.name()
                    )
                    lyr = QgsVectorLayer(sub.uri(), display_name, "ogr")
                    if lyr.isValid():
                        project.addMapLayer(lyr)
                        loaded_count += 1
                        self.log(f"Loaded layer: {display_name}", "INFO")
                self.progressBar.setValue(int(20 + ((idx + 1) / total) * 80))
                QCoreApplication.processEvents()

            if loaded_count > 0:
                if self.iface and hasattr(self.iface, "mapCanvas") and self.iface.mapCanvas():
                    self.iface.mapCanvas().refresh()
                self.log(f"Loaded {loaded_count} layer(s) from '{os.path.basename(folder_path)}'.", "SUCCESS")
                self.project_loaded.emit()
            else:
                self.log("No valid layers could be loaded from the selected folder.", "WARNING")
                self.progressBar.setValue(0)
        except Exception as e:
            self.log(f"Error loading tablet folder: {e}", "ERROR")
            self.progressBar.setValue(0)
        finally:
            self.loadButton.setEnabled(bool(self.comboxFolder3.currentText().strip()))

    def clear_logs(self):
        """Clears execution logs and resets progress bar."""
        if hasattr(self, "logsTextEdit") and self.logsTextEdit:
            self.logsTextEdit.clear()
        if hasattr(self, "progressBar") and self.progressBar:
            self.progressBar.setValue(0)

    def reset_fields(self):
        """Resets directory and cascading dropdowns to default state."""
        self.fileWidget.blockSignals(True)
        self.fileWidget.setFilePath(DEFAULT_DIR)
        self.fileWidget.blockSignals(False)
        self.populate_folder1()
        self.clear_logs()

