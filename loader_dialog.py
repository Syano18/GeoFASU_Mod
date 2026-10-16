# Developer: TechCraft by Chano
# email: c.dacpano@psa.gov.ph
# GeoFASU_Mod - Load and Generate QField Module

import os
import sys
import re
import shutil
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt, QCoreApplication

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsRasterLayer,
    QgsSnappingConfig,
    QgsTolerance,
    QgsLayerTreeGroup,
    QgsLayerTreeLayer,
    Qgis,
)
from qgis.PyQt.QtWidgets import (
    QDialog, QListWidget, QListWidgetItem, QPushButton,
    QVBoxLayout, QHBoxLayout, QLabel, QAbstractItemView,
    QMessageBox
)

from qgis.utils import iface

try:
    from .style import apply_modern_style, setup_dialog_logo
except (ImportError, ValueError):
    from style import apply_modern_style, setup_dialog_logo

# QFieldSync (supports embedded and external plugin installation)
plugin_dir = os.path.dirname(__file__)
if plugin_dir not in sys.path:
    sys.path.insert(0, plugin_dir)

import importlib
for mod_name in ["libqfieldsync.layer", "libqfieldsync.utils.qgis", "qfieldsync.core.cloud_converter"]:
    if mod_name in sys.modules:
        try:
            importlib.reload(sys.modules[mod_name])
        except Exception:
            pass

try:
    from qfieldsync.core.cloud_converter import CloudConverter
    from qfieldsync.core.preferences import Preferences
    HAS_QFIELDSYNC = True
except Exception:
    try:
        from .qfieldsync.core.cloud_converter import CloudConverter
        from .qfieldsync.core.preferences import Preferences
        HAS_QFIELDSYNC = True
    except Exception:
        HAS_QFIELDSYNC = False


FORM_CLASS, _ = uic.loadUiType(os.path.join(os.path.dirname(__file__), 'loader_dialog.ui'))


class LoaderDialog(QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setupUi(self)
        apply_modern_style(self)
        if hasattr(self, 'iconLabel'):
            setup_dialog_logo(self)
        self.plugin_dir = os.path.dirname(__file__)
        self.load_successful = False

        self.aplqml.setEnabled(False)
        self.genrate.setEnabled(False)
        self.progbar.setValue(0)

        self.comboxNOS.setPlaceholderText("-- Select Type of Survey --")
        self.comboxMun.setPlaceholderText("-- Select City/Municipality --")
        self.comboxRep.setPlaceholderText("-- Select Replicate Number --")

        # Signals
        self.fileWidget.fileChanged.connect(self.populate_nos_list)
        self.comboxNOS.currentIndexChanged.connect(self.update_mun_list)
        self.comboxMun.currentIndexChanged.connect(self.update_rep_list)
        self.comboxRep.currentIndexChanged.connect(self.on_rep_change)
        self.loadbtn.clicked.connect(self.load_layers)
        self.aplqml.clicked.connect(self.apply_styles)
        self.genrate.clicked.connect(self.export_qfield_project)

        # Default Reference Directory
        default_ref = r"C:\PSA-GIS\GeoFASU\Kalinga\Project files"
        self.fileWidget.setFilePath(default_ref)
        if os.path.isdir(default_ref):
            self.populate_nos_list()

    # ---------- Utilities ----------
    def _clean(self, s: str) -> str:
        """Windows-safe filename cleaner."""
        s = (s or "").strip()
        s = re.sub(r'[<>:"/\\|?*]+', "_", s)
        return s.rstrip(" .")

    def log(self, message: str, level: str = "INFO"):
        """Appends a line of text to the logs widget with level indicator."""
        prefix = {
            "INFO": "",
            "SUCCESS": "✓ ",
            "WARNING": "⚠ ",
            "ERROR": "✗ ",
        }.get(level.upper(), "")
        if hasattr(self, 'logsTextEdit') and self.logsTextEdit:
            self.logsTextEdit.appendPlainText(f"{prefix}{message}")
            self.logsTextEdit.verticalScrollBar().setValue(
                self.logsTextEdit.verticalScrollBar().maximum()
            )

    def show_error(self, message: str):
        self.load_successful = False
        self.progbar.setValue(0)
        self.remove_all_layers()
        self.loadbtn.setEnabled(True)
        self.aplqml.setEnabled(False)
        self.genrate.setEnabled(False)
        self.log("STATUS: FAILED ✗", "ERROR")
        self.log(f"{message}", "ERROR")
        QCoreApplication.processEvents()

    def remove_all_layers(self):
        project = QgsProject.instance()
        root = project.layerTreeRoot()
        for group_name in ['Tracklog', 'Samples', 'Reference Layer', 'Base Layer', 'Basemap']:
            group = root.findGroup(group_name)
            if group:
                for child in list(group.findLayers()):
                    lyr = child.layer()
                    if lyr:
                        project.removeMapLayer(lyr.id())
                root.removeChildNode(group)

        # Clean up any lingering GeoFASU-related layers from project
        known_keywords = ["Selected SSU", "Additional SSU", "Replacement PSU", "tracklog", "Bgy Bdry."]
        for layer_id, layer in list(project.mapLayers().items()):
            if layer and (any(kw in layer.name() for kw in known_keywords) or layer.name().endswith("_img")):
                project.removeMapLayer(layer_id)

        if hasattr(self, 'iface') and self.iface and self.iface.mapCanvas():
            self.iface.mapCanvas().refresh()

    def reset_fields(self):
        """Resets all input fields and progress bar to their default state."""
        for w in (self.fileWidget, self.comboxNOS, self.comboxMun, self.comboxRep, self.loadbtn):
            w.setEnabled(True)

        default_ref = r"C:\PSA-GIS\GeoFASU\Kalinga\Project files"
        self.fileWidget.setFilePath(default_ref)
        self.comboxNOS.blockSignals(True)
        self.comboxMun.blockSignals(True)
        self.comboxRep.blockSignals(True)
        self.comboxNOS.clear()
        self.comboxMun.clear()
        self.comboxRep.clear()
        self.comboxNOS.setPlaceholderText("-- Select Type of Survey --")
        self.comboxMun.setPlaceholderText("-- Select City/Municipality --")
        self.comboxRep.setPlaceholderText("-- Select Replicate Number --")
        self.comboxNOS.blockSignals(False)
        self.comboxMun.blockSignals(False)
        self.comboxRep.blockSignals(False)
        if os.path.isdir(default_ref):
            self.populate_nos_list()
        self.comboxNOS.setCurrentIndex(-1)
        self.comboxMun.setCurrentIndex(-1)
        self.comboxRep.setCurrentIndex(-1)
        self.progbar.setValue(0)
        self.aplqml.setEnabled(False)
        self.genrate.setEnabled(False)
        self.load_successful = False
        self.clear_logs()

    def clear_logs(self):
        """Clears the execution logs and resets progress bar."""
        if hasattr(self, 'logsTextEdit') and self.logsTextEdit:
            self.logsTextEdit.clear()
        if hasattr(self, 'progbar') and self.progbar:
            self.progbar.setValue(0)

    def reset_all(self):
        """Reset UI and, if load failed, remove added groups."""
        if not self.load_successful:
            self.remove_all_layers()
        self.reset_fields()

    def closeEvent(self, event):
        self.reset_all()
        event.accept()

    def reject(self):
        self.reset_all()
        super().reject()

    def get_reference_layer(self, layer_name: str):
        root = QgsProject.instance().layerTreeRoot()
        ref_group = root.findGroup("Reference Layer")
        if not ref_group:
            return None
        for child in ref_group.children():
            if child.name() == layer_name:
                return child.layer()
        return None

    # ---------- Combos ----------
    def populate_nos_list(self):
        current_selection = self.comboxNOS.currentText().strip()
        self.comboxNOS.blockSignals(True)
        self.comboxMun.blockSignals(True)
        self.comboxRep.blockSignals(True)

        self.comboxNOS.clear()
        self.comboxMun.clear()
        self.comboxRep.clear()
        self.aplqml.setEnabled(False)
        self.genrate.setEnabled(False)
        self.progbar.setValue(0)

        base_path = os.path.join(self.fileWidget.filePath(), 'Projects')
        has_match = False
        if os.path.isdir(base_path):
            dir_list = [d for d in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, d))]
            self.comboxNOS.addItems(dir_list)
            if current_selection and current_selection in dir_list:
                self.comboxNOS.setCurrentText(current_selection)
                has_match = True
            else:
                self.comboxNOS.setCurrentIndex(-1)

        self.comboxNOS.blockSignals(False)
        self.comboxMun.blockSignals(False)
        self.comboxRep.blockSignals(False)

        if has_match:
            self.update_mun_list()

    def update_mun_list(self):
        current_mun = self.comboxMun.currentText().strip()
        self.comboxMun.blockSignals(True)
        self.comboxRep.blockSignals(True)

        self.comboxMun.clear()
        self.comboxRep.clear()
        nos = self.comboxNOS.currentText().strip()
        has_match = False
        if nos:
            base_path = os.path.join(self.fileWidget.filePath(), 'Projects', nos)
            if os.path.isdir(base_path):
                dirs = [d for d in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, d))]
                self.comboxMun.addItems(dirs)
                if current_mun and current_mun in dirs:
                    self.comboxMun.setCurrentText(current_mun)
                    has_match = True
                else:
                    self.comboxMun.setCurrentIndex(-1)

        self.comboxMun.blockSignals(False)
        self.comboxRep.blockSignals(False)

        if has_match:
            self.update_rep_list()

    def update_rep_list(self):
        current_rep = self.comboxRep.currentText().strip()
        self.comboxRep.blockSignals(True)
        self.comboxRep.clear()
        nos = self.comboxNOS.currentText().strip()
        mun = self.comboxMun.currentText().strip()
        if nos and mun:
            base_path = os.path.join(
                self.fileWidget.filePath(), 'Projects',
                nos, mun
            )
            if os.path.isdir(base_path):
                dirs = [d for d in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, d))]
                self.comboxRep.addItems(dirs)
                if current_rep and current_rep in dirs:
                    self.comboxRep.setCurrentText(current_rep)
                else:
                    self.comboxRep.setCurrentIndex(-1)

        self.comboxRep.blockSignals(False)

    def on_rep_change(self):
        if self.comboxRep.currentText().strip():
            self.aplqml.setEnabled(False)
            self.genrate.setEnabled(False)

    # ---------- Load ----------
    def load_layers(self):
        self.logsTextEdit.clear()
        self.log("STATUS: LOADING LAYERS...", "INFO")
        self.loadbtn.setEnabled(False)
        self.progbar.setValue(5)
        QCoreApplication.processEvents()

        try:
            working_dir = os.path.join(self.fileWidget.filePath().strip(), 'Projects')
            nos = self.comboxNOS.currentText().strip()
            mun = self.comboxMun.currentText().strip()
            rep = self.comboxRep.currentText().strip()

            if not all([working_dir, nos, mun, rep]):
                self.show_error("Please make sure all dropdowns are selected.")
                return

            rep_dir = os.path.join(working_dir, nos, mun, rep)
            if not os.path.isdir(rep_dir):
                self.show_error(f"Replicate folder does not exist:\n{rep_dir}")
                return

            # Clean up prior layers before loading
            self.remove_all_layers()
            self.progbar.setValue(15)
            QCoreApplication.processEvents()

            # Create group structure in QGIS project
            root = QgsProject.instance().layerTreeRoot()
            groups = {}
            for gname in ['Tracklog', 'Samples', 'Reference Layer', 'Base Layer', 'Basemap']:
                existing_grp = root.findGroup(gname)
                if existing_grp:
                    root.removeChildNode(existing_grp)
                groups[gname] = root.addGroup(gname)

            self.progbar.setValue(25)
            QCoreApplication.processEvents()

            # 1. Base Layer (Barangay Boundary for mun)
            base_layers_dir = os.path.join(self.fileWidget.filePath().strip(), 'Base Layers')
            if not os.path.isdir(base_layers_dir):
                self.show_error(f"Base Layers folder does not exist:\n{base_layers_dir}")
                return

            base_candidates = [
                f"{mun}.gpkg",
                f"{mun}.shp",
                f"{mun}_bdry.gpkg",
                f"{mun}_bdry.shp",
            ]
            base_layer_path = None
            for cand in base_candidates:
                p = os.path.join(base_layers_dir, cand)
                if os.path.exists(p):
                    base_layer_path = p
                    break

            if not base_layer_path and os.path.isdir(base_layers_dir):
                actual_base = {f.lower(): f for f in os.listdir(base_layers_dir)}
                for cand in base_candidates:
                    if cand.lower() in actual_base:
                        base_layer_path = os.path.join(base_layers_dir, actual_base[cand.lower()])
                        break

            if not base_layer_path and os.path.isdir(base_layers_dir):
                bgy_files = [f for f in os.listdir(base_layers_dir) if f.endswith('.shp') or f.endswith('.gpkg')]
                if bgy_files:
                    base_layer_path = os.path.join(base_layers_dir, bgy_files[0])

            if not base_layer_path or not os.path.exists(base_layer_path):
                self.show_error(f"No Barangay Boundary file found in Base Layers for: {mun}")
                return

            bgy_layer = QgsVectorLayer(base_layer_path, "Bgy Bdry.", "ogr")
            if not bgy_layer.isValid():
                self.show_error(f"Failed to load Barangay Boundary layer: {base_layer_path}")
                return
            QgsProject.instance().addMapLayer(bgy_layer, False)
            groups['Base Layer'].addLayer(bgy_layer)

            self.progbar.setValue(40)
            QCoreApplication.processEvents()

            # 2. Basemap (offline image for mun)
            basemap_dir = os.path.join(self.fileWidget.filePath().strip(), 'Basemap')
            if not os.path.isdir(basemap_dir):
                self.show_error(f"Basemap folder does not exist:\n{basemap_dir}")
                return

            basemap_candidates = [
                f"{mun}_img.gpkg",
                f"{mun}_img.mbtiles",
                f"{mun}_img.tif",
                f"{mun}_img.tiff",
                f"{mun}.gpkg",
                f"{mun}.mbtiles",
                f"{mun}.tif",
                f"{mun}.tiff",
            ]
            basemap_path = None
            for cand in basemap_candidates:
                p = os.path.join(basemap_dir, cand)
                if os.path.exists(p):
                    basemap_path = p
                    break

            if not basemap_path and os.path.isdir(basemap_dir):
                actual_basemaps = {f.lower(): f for f in os.listdir(basemap_dir)}
                for cand in basemap_candidates:
                    if cand.lower() in actual_basemaps:
                        basemap_path = os.path.join(basemap_dir, actual_basemaps[cand.lower()])
                        break

            if not basemap_path:
                self.show_error(f"Offline image file not found in Basemap folder for: {mun}")
                return

            basemap_layer = QgsRasterLayer(basemap_path, f"{mun}_img", "gdal")
            if not basemap_layer.isValid():
                self.show_error(f"Invalid offline image layer: {basemap_path}")
                return

            QgsProject.instance().addMapLayer(basemap_layer, False)
            groups['Basemap'].addLayer(basemap_layer)

            # Collapse basemap children
            for child in groups['Basemap'].children():
                if isinstance(child, QgsLayerTreeLayer):
                    child.setExpanded(False)

            self.progbar.setValue(55)
            QCoreApplication.processEvents()

            # 3. Reference Layer
            ref_path = os.path.join(rep_dir, "Selected SSU_Ref.gpkg")
            if not os.path.exists(ref_path):
                alt_path = os.path.join(rep_dir, f"{nos}_{mun}_Selected SSU_{rep}.gpkg")
                if os.path.exists(alt_path):
                    ref_path = alt_path
                else:
                    self.show_error(f"Reference file not found:\n{ref_path}")
                    return
            ref_layer = QgsVectorLayer(ref_path, "Selected SSU_Ref", "ogr")
            if not ref_layer.isValid():
                self.show_error(f"Invalid reference layer:\n{ref_path}")
                return
            QgsProject.instance().addMapLayer(ref_layer, False)
            groups['Reference Layer'].addLayer(ref_layer)

            self.progbar.setValue(65)
            QCoreApplication.processEvents()

            # 4. Copy and load project sample and tracklog layers
            file_ops = [
                ("selected.gpkg",   f"{nos}_{mun}_Selected SSU_{rep}.gpkg", "Samples",
                 f"{nos}_{mun}_Selected SSU_{rep}"),
                ("additional.gpkg", f"{nos}_{mun}_Additional SSU or Replacement PSU sample.gpkg", "Samples",
                 f"{nos}_{mun}_Additional SSU or Replacement PSU sample"),
                ("tracklog.gpkg",   "tracklog.gpkg", "Tracklog", "tracklog"),
            ]

            step_inc = 25 / len(file_ops)
            for idx, (src_name, dest_name, group_name, layer_name) in enumerate(file_ops):
                src_path = os.path.join(self.plugin_dir, src_name)
                dest_path = os.path.join(rep_dir, dest_name)
                if not os.path.exists(src_path):
                    self.show_error(f"Missing source file: {src_path}")
                    return
                shutil.copyfile(src_path, dest_path)
                lyr = QgsVectorLayer(dest_path, layer_name, "ogr")
                if not lyr.isValid():
                    self.show_error(f"Invalid layer copied to: {dest_path}")
                    return
                QgsProject.instance().addMapLayer(lyr, False)
                groups[group_name].addLayer(lyr)
                self.progbar.setValue(int(65 + (idx + 1) * step_inc))
                QCoreApplication.processEvents()

            # Enable snapping on Selected SSU_Ref
            layer = next((lyr for lyr in QgsProject.instance().mapLayers().values()
                          if lyr.name() == "Selected SSU_Ref"), None)
            if layer:
                cfg = QgsProject.instance().snappingConfig()
                cfg.setEnabled(True)
                cfg.setMode(QgsSnappingConfig.AdvancedConfiguration)

                ils = QgsSnappingConfig.IndividualLayerSettings()
                ils.setEnabled(True)
                ils.setTolerance(10)                 # pixels
                ils.setUnits(QgsTolerance.Pixels)

                if hasattr(ils, "setTypeFlag") and hasattr(Qgis, "SnappingType"):
                    ils.setTypeFlag(Qgis.SnappingTypes(Qgis.SnappingType.Vertex))
                else:
                    ils.setType(QgsSnappingConfig.Vertex)

                cfg.setIndividualLayerSettings(layer, ils)
                QgsProject.instance().setSnappingConfig(cfg)

            self.aplqml.setEnabled(True)
            self.genrate.setEnabled(False)
            self.progbar.setValue(100)
            self.load_successful = True
            self.loadbtn.setEnabled(True)
            QCoreApplication.processEvents()
            # Zoom to Barangay Boundary layer (Base Layer)
            bgy_lyr = None
            if 'Base Layer' in groups:
                for child in groups['Base Layer'].children():
                    if isinstance(child, QgsLayerTreeLayer):
                        lyr = child.layer()
                        if lyr and lyr.isValid():
                            bgy_lyr = lyr
                            break

            if bgy_lyr and self.iface and self.iface.mapCanvas():
                canvas = self.iface.mapCanvas()
                ext = bgy_lyr.extent()
                if ext and not ext.isEmpty():
                    if canvas.mapSettings().destinationCrs() != bgy_lyr.crs():
                        from qgis.core import QgsCoordinateTransform
                        xform = QgsCoordinateTransform(bgy_lyr.crs(), canvas.mapSettings().destinationCrs(), QgsProject.instance())
                        ext = xform.transformBoundingBox(ext)
                    ext.scale(1.05)
                    canvas.setExtent(ext)
                    canvas.refresh()
            elif 'Basemap' in groups and self.iface and self.iface.mapCanvas():
                for child in groups['Basemap'].children():
                    if isinstance(child, QgsLayerTreeLayer):
                        lyr = child.layer()
                        if lyr and lyr.isValid() and not lyr.name().lower().startswith("google"):
                            self.iface.mapCanvas().setExtent(lyr.extent())
                            self.iface.mapCanvas().refresh()
                            break

            QCoreApplication.processEvents()
            self.log("STATUS: COMPLETED ✓", "SUCCESS")
            self.log(f"Layers successfully loaded for {nos} - {mun} (Rep {rep})! ✓", "SUCCESS")
            if self.iface and self.iface.mapCanvas():
                self.iface.mapCanvas().refresh()

        except Exception as e:
            self.show_error(f"Unexpected error: {str(e)}")
        finally:
            self.loadbtn.setEnabled(True)
            if not self.load_successful:
                self.progbar.setValue(0)
                self.aplqml.setEnabled(False)
                self.genrate.setEnabled(False)

    # ---------- Styles ----------
    def apply_styles(self):
        self.loadbtn.setEnabled(False)
        self.progbar.setValue(10)
        QCoreApplication.processEvents()

        try:
            root = QgsProject.instance().layerTreeRoot()
            style_dir = os.path.join(self.plugin_dir, "QML")

            required_groups = ["Basemap", "Reference Layer", "Samples", "Tracklog", "Base Layer"]
            for gname in required_groups:
                group = root.findGroup(gname)
                if not group or not any(
                    isinstance(c, QgsLayerTreeLayer) and c.layer() and c.layer().isValid()
                    for c in group.children()
                ):
                    self.show_error("No/Missing Groups/Layer Loaded. Please load layers first.")
                    return

            def apply_qml(group_name: str, keyword: str, qml_file: str):
                group = root.findGroup(group_name)
                if not group:
                    return
                qml_path = os.path.join(style_dir, qml_file)
                if not os.path.exists(qml_path):
                    return
                for child in group.children():
                    if isinstance(child, QgsLayerTreeLayer):
                        lyr = child.layer()
                        if lyr and (keyword in lyr.name()):
                            lyr.loadNamedStyle(qml_path)
                            lyr.triggerRepaint()

            self.progbar.setValue(25)
            QCoreApplication.processEvents()
            apply_qml("Base Layer", "", "Barangay.qml")
            self.progbar.setValue(45)
            QCoreApplication.processEvents()
            apply_qml("Reference Layer", "", "Reference.qml")
            self.progbar.setValue(65)
            QCoreApplication.processEvents()
            apply_qml("Samples", "_Selected SSU", "Sample.qml")
            apply_qml("Samples", "_Additional", "Additional.qml")
            self.progbar.setValue(85)
            QCoreApplication.processEvents()
            apply_qml("Tracklog", "", "Tracklog.qml")

            # Collapse layers in Samples
            samples_group = root.findGroup("Samples")
            if samples_group:
                for child in samples_group.children():
                    if isinstance(child, QgsLayerTreeLayer):
                        child.setExpanded(False)

            self.progbar.setValue(100)
            self.loadbtn.setEnabled(True)
            self.aplqml.setEnabled(False)
            self.genrate.setEnabled(True)
            QCoreApplication.processEvents()
            self.log("STATUS: COMPLETED ✓", "SUCCESS")
            self.log("QML styles successfully applied to all layers! ✓", "SUCCESS")

        except Exception as e:
            self.show_error(f"Failed to apply styles: {str(e)}")

    # ---------- Export ----------
    def export_qfield_project(self):
        if not HAS_QFIELDSYNC:
            self.log("STATUS: FAILED ✗", "ERROR")
            self.log("QFieldSync plugin is not installed or enabled. Please install QFieldSync to use this export feature.", "ERROR")
            return

        self.log("STATUS: GENERATING QFIELD PROJECT...", "INFO")
        project = QgsProject.instance()

        base_dir = self.fileWidget.filePath()
        if not base_dir:
            self.log("Please select a Reference Directory.", "WARNING")
            return
        base_path = Path(base_dir)

        nos = self._clean(self.comboxNOS.currentText())
        mun = self._clean(self.comboxMun.currentText())
        rep = self._clean(self.comboxRep.currentText())
        if not all([nos, mun, rep]):
            self.log("Please ensure Type of Survey, Municipality, and Replicate Number are selected.", "WARNING")
            return

        layer = self.get_reference_layer("Selected SSU_Ref")
        single_psu_only = False
        single_psu_name = None
        selected_psus_override = None
        if layer:
            idx = layer.fields().lookupField("PSU_Name")
            if idx != -1:
                psu_names = sorted({self._clean(str(f[idx])) for f in layer.getFeatures() if f[idx] not in (None, "")})
                if len(psu_names) == 1:
                    single_psu_only = True
                    single_psu_name = psu_names[0]
                elif len(psu_names) > 1:
                    chosen = self.choose_psus(psu_names)
                    if chosen:
                        selected_psus_override = chosen

        reply = (single_psu_only or bool(selected_psus_override))

        try:
            Preferences().set_value("exportDirectory", str(base_path))
        except Exception:
            pass

        try:
            from qfieldsync.core.cloud_converter import CloudConverter
        except Exception:
            CloudConverter = None

        mbtiles_cache = {}

        def run_convert(inner_folder_name, psu_filter=None, progress_callback=None):
            def set_prog(val, text=""):
                if progress_callback:
                    progress_callback(val)
                else:
                    self.progbar.setValue(val)
                if text:
                    self.progbar.setFormat(f"{text} ({val}%)")
                else:
                    self.progbar.setFormat("%p%")
                QCoreApplication.processEvents()

            set_prog(5, "Initializing...")
            target_root = base_path / "Package for Qfield" / nos
            target_dir = target_root / inner_folder_name
            target_dir.mkdir(parents=True, exist_ok=True)

            import tempfile
            import uuid
            orig_proj_filename = project.fileName()
            temp_proj_path = os.path.join(tempfile.gettempdir(), f"geofasu_temp_{uuid.uuid4().hex[:6]}.qgs")
            project.write(temp_proj_path)
            project.setFileName(orig_proj_filename)

            temp_project = QgsProject()
            temp_project.read(temp_proj_path)
            temp_project.setFileName(str(target_dir / f"{inner_folder_name}.qgs"))

            ref_extent = None
            ref_layer_obj = None
            if psu_filter:
                root = temp_project.layerTreeRoot()
                ref_group = root.findGroup("Reference Layer")
                if ref_group:
                    for child in ref_group.children():
                        if child.name() == "Selected SSU_Ref" and child.layer():
                            ref_layer = child.layer()
                            ref_layer.setSubsetString(f"\"PSU_Name\" = '{psu_filter}'")
                            ref_layer.updateExtents()
                            ref_extent = ref_layer.extent()
                            ref_layer_obj = ref_layer

                            try:
                                from qgis.core import QgsRectangle, QgsReferencedRectangle
                                ext_copy = QgsRectangle(ref_extent)
                                ext_copy.scale(1.2)
                                ref_rect = QgsReferencedRectangle(ext_copy, ref_layer.crs())
                                temp_project.viewSettings().setDefaultViewExtent(ref_rect)
                                temp_project.viewSettings().setPresetExtent(ref_rect)
                            except Exception:
                                pass
                            break

                base_group = root.findGroup("Base Layer")
                base_layer_for_mask = None
                matching_features = []

                if base_group:
                    for child in base_group.children():
                        if isinstance(child, QgsLayerTreeLayer) and child.layer():
                            base_layer_for_mask = child.layer()
                            break

                if base_layer_for_mask and base_layer_for_mask.isValid():
                    from qgis.core import QgsCoordinateTransform, QgsGeometry

                    ref_geoms = []
                    if ref_layer_obj and ref_layer_obj.isValid():
                        xform = None
                        if (
                            ref_layer_obj.crs() != base_layer_for_mask.crs()
                            and ref_layer_obj.crs().isValid()
                            and base_layer_for_mask.crs().isValid()
                        ):
                            xform = QgsCoordinateTransform(
                                ref_layer_obj.crs(),
                                base_layer_for_mask.crs(),
                                temp_project.transformContext(),
                            )
                        for f in ref_layer_obj.getFeatures():
                            g = f.geometry()
                            if g and not g.isEmpty():
                                g_copy = QgsGeometry(g)
                                if xform:
                                    g_copy.transform(xform)
                                ref_geoms.append(g_copy)

                    if ref_geoms:
                        combined_ref = (
                            QgsGeometry.unaryUnion(ref_geoms)
                            if len(ref_geoms) > 1
                            else ref_geoms[0]
                        )
                        for feat in base_layer_for_mask.getFeatures():
                            geom = feat.geometry()
                            if geom and not geom.isEmpty() and geom.intersects(combined_ref):
                                matching_features.append(feat)

                    if not matching_features:
                        field_names = [f.name() for f in base_layer_for_mask.fields()]
                        target_field = "name"
                        for cand in [
                            "name", "NAME", "Bgy_Name", "bgy_name",
                            "BARANGAY", "Barangay", "BGY_NAME", "BRGY_NAME",
                        ]:
                            if cand in field_names:
                                target_field = cand
                                break

                        base_filter = re.split(r'\s*-\s*EA\b', psu_filter, flags=re.IGNORECASE)[0].strip()
                        base_filter_clean = re.sub(
                            r'^\s*(\d+|PSU\s*\d*)\s*[-_:]\s*', '', base_filter, flags=re.IGNORECASE
                        ).strip()
                        parts = re.split(
                            r'\s*\+\s*|\s*/\s*|\s*&\s*|\s+and\s+', base_filter_clean, flags=re.IGNORECASE
                        )

                        for feat in base_layer_for_mask.getFeatures():
                            b_val = str(feat[target_field] or "").strip()
                            if any(p.strip().lower() in b_val.lower() for p in parts if p.strip()):
                                matching_features.append(feat)

                    if matching_features:
                        sql_escaped = []
                        for f in matching_features:
                            val = f["name"] if "name" in [fld.name() for fld in base_layer_for_mask.fields()] else f[target_field]
                            val_str = str(val).replace("'", "''")
                            sql_escaped.append(f"'{val_str}'")
                        match_field = "name" if "name" in [fld.name() for fld in base_layer_for_mask.fields()] else target_field
                        expr = f"\"{match_field}\" IN ({','.join(sql_escaped)})"
                        base_layer_for_mask.setSubsetString(expr)

            # Determine mask features for Basemap clipping
            mask_features = []
            if matching_features:
                mask_features = matching_features
            elif base_layer_for_mask and base_layer_for_mask.isValid():
                ref_lyr = self.get_reference_layer("Selected SSU_Ref")
                if ref_lyr and ref_lyr.isValid():
                    from qgis.core import QgsCoordinateTransform, QgsGeometry
                    xform = None
                    if ref_lyr.crs() != base_layer_for_mask.crs() and ref_lyr.crs().isValid() and base_layer_for_mask.crs().isValid():
                        xform = QgsCoordinateTransform(ref_lyr.crs(), base_layer_for_mask.crs(), temp_project.transformContext())
                    ref_geoms = []
                    for f in ref_lyr.getFeatures():
                        g = f.geometry()
                        if g and not g.isEmpty():
                            g_c = QgsGeometry(g)
                            if xform:
                                g_c.transform(xform)
                            ref_geoms.append(g_c)
                    if ref_geoms:
                        comb = QgsGeometry.unaryUnion(ref_geoms) if len(ref_geoms) > 1 else ref_geoms[0]
                        for feat in base_layer_for_mask.getFeatures():
                            gm = feat.geometry()
                            if gm and not gm.isEmpty() and gm.intersects(comb):
                                mask_features.append(feat)

                if not mask_features:
                    mask_features = list(base_layer_for_mask.getFeatures())

            # Clip Basemap and convert to MBTiles
            basemap_group = root.findGroup("Basemap")
            if basemap_group and mask_features and base_layer_for_mask and base_layer_for_mask.isValid():
                for child in basemap_group.children():
                    if isinstance(child, QgsLayerTreeLayer) and child.layer():
                        set_prog(25)
                        raster_layer = child.layer()
                        import tempfile
                        import uuid
                        from osgeo import gdal
                        from qgis.core import (
                            QgsVectorLayer,
                            QgsFeature,
                            QgsGeometry,
                            QgsRasterLayer,
                            QgsCoordinateTransform,
                            QgsVectorFileWriter
                        )

                        raster_crs = raster_layer.crs()
                        base_crs = base_layer_for_mask.crs()
                        xform = None
                        if raster_crs.isValid() and base_crs.isValid() and raster_crs != base_crs:
                            xform = QgsCoordinateTransform(base_crs, raster_crs, temp_project.transformContext())

                        crs_auth = raster_crs.authid() if raster_crs.isValid() else base_crs.authid()
                        mask_memory_layer = QgsVectorLayer(f"MultiPolygon?crs={crs_auth}", "barangay_mask", "memory")
                        dp = mask_memory_layer.dataProvider()

                        mask_feats = []
                        for feat in mask_features:
                            geom = feat.geometry()
                            if geom and not geom.isEmpty():
                                g_copy = QgsGeometry(geom)
                                if xform:
                                    g_copy.transform(xform)
                                f_new = QgsFeature()
                                f_new.setGeometry(g_copy)
                                mask_feats.append(f_new)

                        if mask_feats:
                            dp.addFeatures(mask_feats)
                            mask_memory_layer.updateExtents()

                            temp_mask_path = os.path.join(
                                tempfile.gettempdir(),
                                f"mask_{inner_folder_name}_{uuid.uuid4().hex[:6]}.gpkg"
                            )
                            QgsVectorFileWriter.writeAsVectorFormat(
                                mask_memory_layer, temp_mask_path, "UTF-8", raster_crs, "GPKG"
                            )

                            mask_key = None
                            if mask_features:
                                mask_key = "_".join(sorted(str(f["name"] if "name" in [fld.name() for fld in base_layer_for_mask.fields()] else f.id()) for f in mask_features))

                            dest_mbtiles_path = str(target_dir / f"{raster_layer.name()}.mbtiles")

                            # Fast path: Reuse already-clipped MBTiles if identical mask features were processed in this batch
                            if mask_key and mask_key in mbtiles_cache and os.path.exists(mbtiles_cache[mask_key]):
                                set_prog(35, "Reusing cached basemap...")
                                shutil.copyfile(mbtiles_cache[mask_key], dest_mbtiles_path)
                                new_raster = QgsRasterLayer(dest_mbtiles_path, raster_layer.name(), "gdal")
                                if new_raster.isValid():
                                    temp_project.addMapLayer(new_raster, False)
                                    basemap_group.insertLayer(0, new_raster)
                                    temp_project.removeMapLayer(raster_layer.id())
                                break

                            extent = mask_memory_layer.extent()
                            bounds = [extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum()]

                            temp_tif_path = os.path.join(
                                tempfile.gettempdir(),
                                f"{raster_layer.name()}_{inner_folder_name}_{uuid.uuid4().hex[:6]}.tif"
                            )

                            try:
                                gdal.SetCacheMax(1024 * 1024 * 1024)
                                gdal.SetConfigOption('GDAL_NUM_THREADS', 'ALL_CPUS')

                                def warp_cb(complete, message, unknown):
                                    p = int(20 + complete * 20)
                                    set_prog(p, "Clipping basemap...")
                                    return 1

                                gdal.Warp(
                                    temp_tif_path,
                                    raster_layer.source(),
                                    format='GTiff',
                                    outputBounds=bounds,
                                    cutlineDSName=temp_mask_path,
                                    cropToCutline=True,
                                    dstSRS=raster_crs.authid() if raster_crs.isValid() else None,
                                    warpOptions=['NUM_THREADS=ALL_CPUS'],
                                    creationOptions=['COMPRESS=JPEG', 'JPEG_QUALITY=80', 'TILED=YES', 'NUM_THREADS=ALL_CPUS'],
                                    callback=warp_cb
                                )

                                if os.path.exists(temp_tif_path):
                                    def trans_cb(complete, message, unknown):
                                        p = int(40 + complete * 15)
                                        set_prog(p, "Converting to MBTiles...")
                                        return 1

                                    gdal.Translate(
                                        dest_mbtiles_path,
                                        temp_tif_path,
                                        format='MBTILES',
                                        creationOptions=['TILE_FORMAT=JPEG', 'QUALITY=80', 'ZOOM_LEVEL_STRATEGY=AUTO', 'NUM_THREADS=ALL_CPUS'],
                                        callback=trans_cb
                                    )

                                    if os.path.exists(dest_mbtiles_path):
                                        def ov_cb(complete, message, unknown):
                                            p = int(55 + complete * 10)
                                            set_prog(p, "Building overviews...")
                                            return 1

                                        ds = gdal.Open(dest_mbtiles_path, gdal.GA_Update)
                                        if ds:
                                            ds.BuildOverviews("NEAREST", [2, 4, 8], callback=ov_cb)
                                            ds = None

                                        if mask_key and os.path.exists(dest_mbtiles_path):
                                            mbtiles_cache[mask_key] = dest_mbtiles_path

                                        new_raster = QgsRasterLayer(dest_mbtiles_path, raster_layer.name(), "gdal")
                                        if new_raster.isValid():
                                            temp_project.addMapLayer(new_raster, False)
                                            basemap_group.insertLayer(0, new_raster)
                                            temp_project.removeMapLayer(raster_layer.id())

                                    try:
                                        if os.path.exists(temp_tif_path):
                                            os.remove(temp_tif_path)
                                    except Exception:
                                        pass

                                try:
                                    if os.path.exists(temp_mask_path):
                                        os.remove(temp_mask_path)
                                except Exception:
                                    pass
                            except Exception as e:
                                print(f"Basemap clip to mbtiles failed: {e}")
                        break

            set_prog(65, "Packaging QField project...")
            try:
                cc = CloudConverter(temp_project, str(target_dir))
                setattr(cc, "open_project_after_convert", False)
                cc.total_progress_updated.connect(
                    lambda cur, tot, msg: set_prog(int(65 + (cur / max(tot, 1)) * 30), "Writing QField project...")
                )
                cc.convert()
            finally:
                try:
                    if os.path.exists(temp_proj_path):
                        os.remove(temp_proj_path)
                except Exception:
                    pass

            set_prog(100, "Done")
            return target_dir

        if not reply:
            self.genrate.setEnabled(False)
            self.loadbtn.setEnabled(False)
            self.progbar.setValue(10)
            self.progbar.setFormat("Exporting... %p%")
            QCoreApplication.processEvents()
            inner_name = f"{nos}_{mun}_Selected SSU_{rep}"
            try:
                def make_single_cb(p):
                    self.progbar.setValue(p)
                    QCoreApplication.processEvents()

                out_target = run_convert(inner_name, progress_callback=make_single_cb)
                self.progbar.setValue(100)
                self.progbar.setFormat("%p%")
                self.genrate.setEnabled(False)
                self.loadbtn.setEnabled(True)
                self.log(f"Successfully generated QField project: {inner_name}! ✓", "SUCCESS")
                self.log(f"Export Location: {out_target}", "INFO")
            except Exception as e:
                self.progbar.setValue(0)
                self.progbar.setFormat("%p%")
                self.genrate.setEnabled(True)
                self.loadbtn.setEnabled(True)
                self.log(f"Export Failed: {str(e)}", "ERROR")
            return

        if not layer:
            self.log("Reference layer 'Selected SSU_Ref' not found in project.", "ERROR")
            return

        idx = layer.fields().lookupField("PSU_Name")
        if idx == -1:
            self.log("Field 'PSU_Name' not found in Selected SSU_Ref.", "ERROR")
            return

        psu_names = sorted({self._clean(str(f[idx])) for f in layer.getFeatures() if f[idx] not in (None, "")})
        if not psu_names:
            self.log("No PSU_Name values found in Reference layer.", "ERROR")
            return

        if single_psu_only:
            selected_psus = [single_psu_name]
        else:
            selected_psus = selected_psus_override if selected_psus_override else psu_names

        self.genrate.setEnabled(False)
        self.loadbtn.setEnabled(False)
        self.progbar.setValue(0)
        QCoreApplication.processEvents()

        success, fail = 0, 0
        failed_errors = []
        total = len(selected_psus)
        for i, psu in enumerate(selected_psus):
            def make_cb(index, psu_name):
                def cb(p):
                    overall = int(((index + (p / 100)) / total) * 100)
                    self.progbar.setValue(overall)
                    self.progbar.setFormat(f"Exporting {psu_name} ({index+1}/{total}): {overall}%")
                    QCoreApplication.processEvents()
                return cb

            inner_folder = f"{nos}_{mun}_Selected SSU_{rep}_{psu}"
            try:
                _ = run_convert(inner_folder, psu_filter=psu, progress_callback=make_cb(i, psu))
                success += 1
            except Exception as e:
                fail += 1
                err_str = f"PSU '{psu}': {str(e)}"
                failed_errors.append(err_str)
                import traceback
                print(f"Export error for {psu}:\n{traceback.format_exc()}")

        self.progbar.setValue(100)
        self.progbar.setFormat("%p%")
        self.loadbtn.setEnabled(True)
        if fail > 0:
            self.genrate.setEnabled(True)
            self.log("STATUS: FAILED ✗", "ERROR")
            err_msg = "; ".join(failed_errors[:4])
            self.log(f"Export Issues: Generated {success} of {total} QField Project(s). Errors: {err_msg}", "ERROR")
        else:
            self.genrate.setEnabled(False)
            self.log("STATUS: COMPLETED ✓", "SUCCESS")
            self.log(f"Export Finished: Successfully generated all {success} QField Project(s)! ✓", "SUCCESS")

    def choose_psus(self, psu_list):
        """Displays selection dialog for PSUs."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Select PSU Name(s)")
        dlg.resize(360, 440)
        apply_modern_style(dlg)

        label = QLabel("Select one or more PSU Names to export:")
        listw = QListWidget()
        listw.setSelectionMode(QAbstractItemView.ExtendedSelection)
        for name in psu_list:
            item = QListWidgetItem(name)
            listw.addItem(item)
            item.setSelected(True)

        btn_ok = QPushButton("Export")
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setProperty("secondary", True)
        btn_all = QPushButton("Select All")
        btn_all.setProperty("secondary", True)
        btn_clear = QPushButton("Clear")
        btn_clear.setProperty("secondary", True)

        btn_all.clicked.connect(listw.selectAll)
        btn_clear.clicked.connect(listw.clearSelection)
        btn_ok.clicked.connect(dlg.accept)
        btn_cancel.clicked.connect(dlg.reject)

        btns_left = QHBoxLayout()
        btns_left.addWidget(btn_all)
        btns_left.addWidget(btn_clear)
        btns_left.addStretch()

        btns = QHBoxLayout()
        btns.addStretch()
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)

        layout = QVBoxLayout(dlg)
        layout.addWidget(label)
        layout.addWidget(listw)
        layout.addLayout(btns_left)
        layout.addLayout(btns)

        if dlg.exec_() == QDialog.Accepted:
            return [it.text() for it in listw.selectedItems()]
        return []