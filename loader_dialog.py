# Developer: TechCraft by Chano
# email: c.dacpano@psa.gov.ph
# GeoFASU_Mod - Load Layers Module

import os
import sys
import re
import shutil
from pathlib import Path

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
    QDialog, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QMessageBox
)

from qgis.utils import iface

try:
    from .style import apply_modern_style, setup_dialog_logo
except (ImportError, ValueError):
    from style import apply_modern_style, setup_dialog_logo

FORM_CLASS, _ = uic.loadUiType(os.path.join(os.path.dirname(__file__), 'loader_dialog.ui'))


class LoaderDialog(QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setupUi(self)
        apply_modern_style(self)
        setup_dialog_logo(self)
        self.plugin_dir = os.path.dirname(__file__)
        self.load_successful = False

        self.progbar.setValue(0)

        self.comboxNOS.setPlaceholderText("-- Select Type of Survey --")
        self.comboxMun.setPlaceholderText("-- Select City/Municipality --")
        self.comboxRep.setPlaceholderText("-- Select Replicate Number --")

        # Signals
        self.fileWidget.fileChanged.connect(self.populate_nos_list)
        self.comboxNOS.currentIndexChanged.connect(self.update_mun_list)
        self.comboxMun.currentIndexChanged.connect(self.update_rep_list)
        self.loadbtn.clicked.connect(self.load_layers)

    # ---------- Utilities ----------
    def _clean(self, s: str) -> str:
        """Windows-safe filename cleaner."""
        s = (s or "").strip()
        s = re.sub(r'[<>:"/\\|?*]+', "_", s)
        return s.rstrip(" .")

    def show_error(self, message: str):
        self.load_successful = False
        self.progbar.setValue(0)
        self.remove_all_layers()
        self.loadbtn.setEnabled(True)
        QCoreApplication.processEvents()
        QMessageBox.critical(self, "Error", message)

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

    def reset_all(self):
        """Reset UI and, if load failed, remove added groups."""
        if not self.load_successful:
            self.remove_all_layers()

        for w in (self.fileWidget, self.comboxNOS, self.comboxMun, self.comboxRep, self.loadbtn):
            w.setEnabled(True)

        self.fileWidget.setFilePath("")
        self.comboxNOS.clear()
        self.comboxMun.clear()
        self.comboxRep.clear()
        self.progbar.setValue(0)
        self.load_successful = False

    def closeEvent(self, event):
        self.reset_all()
        event.accept()

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
        self.comboxNOS.blockSignals(True)
        self.comboxMun.blockSignals(True)
        self.comboxRep.blockSignals(True)

        self.comboxNOS.clear()
        self.comboxMun.clear()
        self.comboxRep.clear()
        self.progbar.setValue(0)

        base_path = os.path.join(self.fileWidget.filePath(), 'Projects')
        if os.path.isdir(base_path):
            dir_list = [d for d in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, d))]
            self.comboxNOS.addItems(dir_list)
            self.comboxNOS.setCurrentIndex(-1)

        self.comboxNOS.blockSignals(False)
        self.comboxMun.blockSignals(False)
        self.comboxRep.blockSignals(False)

    def update_mun_list(self):
        self.comboxMun.blockSignals(True)
        self.comboxRep.blockSignals(True)

        self.comboxMun.clear()
        self.comboxRep.clear()
        nos = self.comboxNOS.currentText().strip()
        if nos:
            base_path = os.path.join(self.fileWidget.filePath(), 'Projects', nos)
            if os.path.isdir(base_path):
                dirs = [d for d in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, d))]
                self.comboxMun.addItems(dirs)
                self.comboxMun.setCurrentIndex(-1)

        self.comboxMun.blockSignals(False)
        self.comboxRep.blockSignals(False)

    def update_rep_list(self):
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
                self.comboxRep.setCurrentIndex(-1)

        self.comboxRep.blockSignals(False)

    # ---------- Load ----------
    def load_layers(self):
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

            # 1. Base Layer (Barangay Boundary)
            base_layers_dir = os.path.join(self.fileWidget.filePath(), 'Base Layers')
            if not os.path.isdir(base_layers_dir):
                self.show_error("Base Layers folder does not exist.")
                return

            bgy_files = [f for f in os.listdir(base_layers_dir) if f.endswith('.shp') or f.endswith('.gpkg')]
            if not bgy_files:
                self.show_error("No Barangay Boundary shapefile or geopackage found in Base Layers.")
                return

            bgy_path = os.path.join(base_layers_dir, bgy_files[0])
            bgy_layer = QgsVectorLayer(bgy_path, "Bgy Bdry.", "ogr")
            if not bgy_layer.isValid():
                self.show_error(f"Failed to load Barangay Boundary layer: {bgy_path}")
                return
            QgsProject.instance().addMapLayer(bgy_layer, False)
            groups['Base Layer'].addLayer(bgy_layer)

            self.progbar.setValue(40)
            QCoreApplication.processEvents()

            # 2. Basemap (Imagery/Raster or Google Satellite XYZ)
            basemap_dir = os.path.join(self.fileWidget.filePath(), 'Basemap')
            ortho_loaded = False
            if os.path.isdir(basemap_dir):
                ortho_candidates = [
                    f for f in os.listdir(basemap_dir)
                    if f.lower().endswith(('.tif', '.tiff', '.ecw', '.img', '.vrt'))
                ]
                if ortho_candidates:
                    ortho_path = os.path.join(basemap_dir, ortho_candidates[0])
                    ortho_lyr = QgsRasterLayer(ortho_path, f"{mun}_img", "gdal")
                    if ortho_lyr.isValid():
                        QgsProject.instance().addMapLayer(ortho_lyr, False)
                        groups['Basemap'].addLayer(ortho_lyr)
                        ortho_loaded = True

            if not ortho_loaded:
                # Fallback to Google Satellite XYZ layer
                xyz_url = (
                    "type=xyz&url=https://mt1.google.com/vt/lyrs%3Ds%26x%3D%7Bx%7D%26y%3D%7By%7D%26z%3D%7Bz%7D"
                    "&zmax=19&zmin=0"
                )
                sat_layer = QgsRasterLayer(xyz_url, "Google Satellite", "wms")
                if sat_layer.isValid():
                    QgsProject.instance().addMapLayer(sat_layer, False)
                    groups['Basemap'].addLayer(sat_layer)

            self.progbar.setValue(55)
            QCoreApplication.processEvents()

            # 3. Reference Layer
            ref_path = os.path.join(rep_dir, f"{nos}_{mun}_Selected SSU_{rep}.gpkg")
            if not os.path.exists(ref_path):
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

            self.progbar.setValue(100)
            self.load_successful = True
            self.loadbtn.setEnabled(True)
            QCoreApplication.processEvents()
            QMessageBox.information(self, "Success", "Layers successfully loaded.")

            # Zoom to first valid layer in Basemap
            for child in groups['Basemap'].children():
                if isinstance(child, QgsLayerTreeLayer):
                    lyr = child.layer()
                    if lyr and lyr.isValid():
                        self.iface.mapCanvas().setExtent(lyr.extent())
                        self.iface.mapCanvas().refresh()
                        break

        except Exception as e:
            self.show_error(f"Unexpected error: {str(e)}")
        finally:
            self.loadbtn.setEnabled(True)
            if not self.load_successful:
                self.progbar.setValue(0)