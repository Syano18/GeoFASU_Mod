# Author: Mapping_Kalinga
# email: c.dacpano@psa.gov.ph

import os
import re
import shutil
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt

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
    QMessageBox, QInputDialog
)

from qgis.utils import iface

# QFieldSync
try:
    from qfieldsync.core.cloud_converter import CloudConverter
    from qfieldsync.core.preferences import Preferences
    HAS_QFIELDSYNC = True
except ImportError:
    HAS_QFIELDSYNC = False


FORM_CLASS, _ = uic.loadUiType(os.path.join(os.path.dirname(__file__), 'loader_dialog.ui'))


class LoaderDialog(QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setupUi(self)
        self.plugin_dir = os.path.dirname(__file__)
        self.load_successful = False

        self.aplqml.setEnabled(False)
        self.genrate.setEnabled(False)
        self.progbar.setValue(0)

        # Signals
        self.fileWidget.fileChanged.connect(self.populate_nos_list)
        self.comboxNOS.currentIndexChanged.connect(self.update_mun_list)
        self.comboxMun.currentIndexChanged.connect(self.update_rep_list)
        self.comboxRep.currentIndexChanged.connect(self.on_rep_change)
        self.loadbtn.clicked.connect(self.load_layers)
        self.aplqml.clicked.connect(self.apply_styles)
        self.genrate.clicked.connect(self.export_qfield_project)

    # ---------- Utilities ----------
    def _clean(self, s: str) -> str:
        """Windows-safe filename cleaner."""
        s = (s or "").strip()
        s = re.sub(r'[<>:"/\\|?*]+', "_", s)
        return s.rstrip(" .")

    def show_error(self, message: str):
        QMessageBox.critical(self, "Error", message)
        self.load_successful = False

    def remove_all_layers(self):
        root = QgsProject.instance().layerTreeRoot()
        for group_name in ['Basemap', 'Base Layer', 'Reference Layer', 'Samples', 'Tracklog']:
            group = root.findGroup(group_name)
            if group:
                root.removeChildNode(group)

    def reset_all(self):
        """Reset UI and, if load failed, remove added groups."""
        if not self.load_successful:
            self.remove_all_layers()

        for w in (self.fileWidget, self.comboxNOS, self.comboxMun, self.comboxRep,
                  self.loadbtn, self.aplqml, self.genrate):
            w.setEnabled(True)

        self.fileWidget.setFilePath("")
        self.comboxNOS.clear()
        self.comboxMun.clear()
        self.comboxRep.clear()
        self.progbar.setValue(0)
        self.aplqml.setEnabled(False)
        self.genrate.setEnabled(False)
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
        self.comboxNOS.clear(); self.comboxMun.clear(); self.comboxRep.clear()
        self.aplqml.setEnabled(False); self.progbar.setValue(0)

        base_path = os.path.join(self.fileWidget.filePath(), 'Projects')
        if not os.path.isdir(base_path):
            return
        dir_list = [d for d in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, d))]
        self.comboxNOS.addItem("")
        self.comboxNOS.addItems(dir_list)

    def update_mun_list(self):
        self.comboxMun.clear(); self.comboxRep.clear()
        nos = self.comboxNOS.currentText().strip()
        base_path = os.path.join(self.fileWidget.filePath(), 'Projects', nos)
        if not os.path.isdir(base_path):
            return
        dirs = [d for d in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, d))]
        self.comboxMun.addItem("")
        self.comboxMun.addItems(dirs)

    def update_rep_list(self):
        self.comboxRep.clear()
        base_path = os.path.join(
            self.fileWidget.filePath(), 'Projects',
            self.comboxNOS.currentText().strip(),
            self.comboxMun.currentText().strip()
        )
        if not os.path.isdir(base_path):
            return
        dirs = [d for d in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, d))]
        self.comboxRep.addItem("")
        self.comboxRep.addItems(dirs)

    def on_rep_change(self):
        if self.comboxRep.currentText().strip():
            self.aplqml.setEnabled(False)

    # ---------- Load ----------
    def load_layers(self):
        try:
            working_dir = os.path.join(self.fileWidget.filePath().strip(), 'Projects')
            nos = self.comboxNOS.currentText().strip()
            mun = self.comboxMun.currentText().strip()
            rep = self.comboxRep.currentText().strip()
            if not all([working_dir, nos, mun, rep]):
                self.show_error("All inputs must be selected.")
                return

            self.progbar.setValue(10)
            self.remove_all_layers()
            self.progbar.setValue(20)

            root = QgsProject.instance().layerTreeRoot()
            groups = {name: root.addGroup(name) for name in
                      ['Tracklog', 'Samples', 'Reference Layer', 'Base Layer', 'Basemap']}

            # Basemap (offline image)
            basemap_path = os.path.join(self.fileWidget.filePath().strip(), 'Basemap', f"{mun}_img.gpkg")
            if not os.path.exists(basemap_path):
                self.show_error(f"Offline image file not found: {basemap_path}")
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

            self.progbar.setValue(30)

            # Base Layer
            base_layer_path = os.path.join(self.fileWidget.filePath().strip(), 'Base Layers', f"{mun}.gpkg")
            base_layer = QgsVectorLayer(base_layer_path, "Bgy Bdry.", "ogr")
            if not base_layer.isValid():
                self.show_error(f"Invalid base layer: {base_layer_path}")
                return

            QgsProject.instance().addMapLayer(base_layer, False)
            groups['Base Layer'].addLayer(base_layer)

            self.progbar.setValue(40)

            # Reference Layer
            ref_layer_path = os.path.join(working_dir, nos, mun, rep, "Selected SSU_Ref.gpkg")
            if not os.path.exists(ref_layer_path):
                self.show_error(f"Missing reference layer: {ref_layer_path}")
                return

            ref_layer = QgsVectorLayer(ref_layer_path, "Selected SSU_Ref", "ogr")
            if not ref_layer.isValid():
                self.show_error("Invalid reference layer.")
                return

            QgsProject.instance().addMapLayer(ref_layer, False)
            groups['Reference Layer'].addLayer(ref_layer)
            self.progbar.setValue(60)

            # Copy & load additional files to Samples/Tracklog
            rep_dir = os.path.join(working_dir, nos, mun, rep)
            file_ops = [
                ("selected.gpkg",   f"{nos}_{mun}_Selected SSU_{rep}.gpkg", "Samples",
                 f"{nos}_{mun}_Selected SSU_{rep}"),
                ("additional.gpkg", f"{nos}_{mun}_Additional SSU or Replacement PSU sample.gpkg", "Samples",
                 f"{nos}_{mun}_Additional SSU or Replacement PSU sample"),
                ("tracklog.gpkg",   "tracklog.gpkg", "Tracklog", "tracklog"),
            ]

            for src_name, dest_name, group_name, layer_name in file_ops:
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

            self.progbar.setValue(90)

            # Enable snapping on Selected SSU_Ref (works on old & new QGIS APIs)
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

                # Newer QGIS (≥ ~3.12): setTypeFlag with Qgis.SnappingTypes
                # Older QGIS: setType with QgsSnappingConfig.Vertex (deprecated but present)
                if hasattr(ils, "setTypeFlag") and hasattr(Qgis, "SnappingType"):
                    ils.setTypeFlag(Qgis.SnappingTypes(Qgis.SnappingType.Vertex))
                else:
                    ils.setType(QgsSnappingConfig.Vertex)

                cfg.setIndividualLayerSettings(layer, ils)
                QgsProject.instance().setSnappingConfig(cfg)

            self.aplqml.setEnabled(True)
            self.progbar.setValue(100)
            self.genrate.setEnabled(False)
            self.load_successful = True
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

    # ---------- Styles ----------
    def apply_styles(self):
        self.loadbtn.setEnabled(False)
        try:
            root = QgsProject.instance().layerTreeRoot()
            style_dir = os.path.join(self.plugin_dir, "QML")

            required_groups = ["Basemap", "Reference Layer", "Samples", "Tracklog", "Base Layer"]
            # verify each group has at least one valid layer
            for gname in required_groups:
                group = root.findGroup(gname)
                if not group or not any(
                    isinstance(c, QgsLayerTreeLayer) and c.layer() and c.layer().isValid()
                    for c in group.children()
                ):
                    QMessageBox.critical(self, "Error", "No/Missing Groups/Layer Loaded")
                    self.aplqml.setEnabled(False)
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

            apply_qml("Base Layer", "", "Barangay.qml")
            apply_qml("Reference Layer", "", "Reference.qml")
            apply_qml("Samples", "_Selected SSU", "Sample.qml")
            apply_qml("Samples", "_Additional", "Additional.qml")
            apply_qml("Tracklog", "", "Tracklog.qml")   # ✅ fixed typo

            QMessageBox.information(self, "Style Applied", "QML styles successfully applied.")

            # collapse layers in Samples
            samples_group = root.findGroup("Samples")
            if samples_group:
                for child in samples_group.children():
                    if isinstance(child, QgsLayerTreeLayer):
                        child.setExpanded(False)

            self.aplqml.setEnabled(False)
            self.genrate.setEnabled(True)
            self.fileWidget.setEnabled(False)
            self.comboxNOS.setEnabled(False)
            self.comboxMun.setEnabled(False)
            self.comboxRep.setEnabled(False)

        except Exception as e:
            self.show_error(f"Failed to apply styles: {str(e)}")

    # ---------- Export ----------
    def export_qfield_project(self):
        if not HAS_QFIELDSYNC:
            QMessageBox.critical(self, "Error", "QFieldSync plugin is not installed or enabled. Please install QFieldSync to use this export feature.")
            return

        project = QgsProject.instance()

        base_dir = self.fileWidget.filePath()
        if not base_dir:
            QMessageBox.critical(self, "Error", "Please select an output folder.")
            return
        base_path = Path(base_dir)

        nos = self._clean(self.comboxNOS.currentText())
        mun = self._clean(self.comboxMun.currentText())
        rep = self._clean(self.comboxRep.currentText())
        if not all([nos, mun, rep]):
            QMessageBox.critical(self, "Error", "NOS, MUN, and REP must be selected.")
            return

        # ---------- Lock non-sample layers ----------
        def lock_non_sample_layers():
            """Set all layers except those under 'Samples' as read-only and non-identifiable."""
            root = QgsProject.instance().layerTreeRoot()
            sample_group = root.findGroup("Samples")
            sample_layers = set()
            if sample_group:
                for child in sample_group.children():
                    if isinstance(child, QgsLayerTreeLayer) and child.layer():
                        sample_layers.add(child.layer().id())

            for layer in QgsProject.instance().mapLayers().values():
                if layer.id() not in sample_layers:
                    try:
                        # Disable identify
                        layer.setCustomProperty("identify/disabled", True)
                        # Set read-only
                        layer.setReadOnly(True)
                    except Exception:
                        pass

        # ---------- Detect PSU count before asking ----------
        layer = self.get_reference_layer("Selected SSU_Ref")
        single_psu_only = False
        single_psu_name = None
        if layer:
            idx = layer.fields().lookupField("PSU_Name")
            if idx != -1:
                psu_names = sorted({self._clean(str(f[idx])) for f in layer.getFeatures() if f[idx] not in (None, "")})
                if len(psu_names) == 1:
                    single_psu_only = True
                    single_psu_name = psu_names[0]

        # ---------- Ask only if more than one PSU ----------
        if single_psu_only:
            reply = QMessageBox.Yes  # Route single PSUs into the batch flow
        else:
            reply = QMessageBox.question(
                self, "Export by PSU?",
                "Do you want to export separately by PSU name?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )

        # Remember last directory
        try:
            Preferences().set_value("exportDirectory", str(base_path))
        except Exception:
            pass

        def run_convert(inner_folder_name, psu_filter=None):
            """
            Creates <base_path>/Package for Qfield/<nos>/<inner_folder_name>,
            optionally filters 'Selected SSU_Ref' by PSU,
            renames '*_attachments.zip' -> 'attachments.zip',
            packs produced .qgs into <inner_folder_name>.qgz (ONLY),
            safely restores filter; returns path to the .qgz.
            """
            target_root = base_path / "Package for Qfield" / nos
            target_dir = target_root / inner_folder_name
            target_dir.mkdir(parents=True, exist_ok=True)

            val_root = base_path / "Validation Output" / nos / mun
            val_root.mkdir(parents=True, exist_ok=True)

            import time
            import tempfile
            import qgis.utils
            from qgis.core import QgsProject, QgsLayerTreeLayer
            import gc

            temp_proj_path = str(base_path / "geofasu_temp_export.qgz")
            project.write(temp_proj_path)
            
            temp_project = QgsProject()
            temp_project.read(temp_proj_path)
            # Make sure baseName is set for CloudConverter so qgs filename is clean
            temp_project.setFileName(str(target_dir / f"{inner_folder_name}.qgz"))

            ref_extent = None
            if psu_filter:
                root = temp_project.layerTreeRoot()
                # Filter Reference Layer
                ref_group = root.findGroup("Reference Layer")
                if ref_group:
                    for child in ref_group.children():
                        if child.name() == "Selected SSU_Ref" and child.layer():
                            ref_layer = child.layer()
                            ref_layer.setSubsetString(f"\"PSU_Name\" = '{psu_filter}'")
                            ref_layer.updateExtents()
                            ref_extent = ref_layer.extent()
                            
                            try:
                                from qgis.core import QgsRectangle, QgsReferencedRectangle
                                ext_copy = QgsRectangle(ref_extent)
                                ext_copy.scale(1.2)
                                ref_rect = QgsReferencedRectangle(ext_copy, ref_layer.crs())
                                temp_project.viewSettings().setDefaultViewExtent(ref_rect)
                                temp_project.viewSettings().setPresetExtent(ref_rect)
                            except Exception as e:
                                print(f"Set view extent error: {e}")
                            break
                # Filter Sample Layer
                sample_group = root.findGroup("Samples")
                sample_layer_name = f"{nos}_{mun}_Selected SSU_{rep}"
                if sample_group:
                    for child in sample_group.children():
                        if child.name() == sample_layer_name and child.layer():
                            child.layer().setSubsetString(f"\"PSU_Name\" = '{psu_filter}'")
                            break
                # Filter Base Layer
                import re
                base_filter = re.split(r'\s*-\s*EA\s*', psu_filter, flags=re.IGNORECASE)[0]
                base_filter = re.sub(r'\(.*?\)', '', base_filter)  # strip parentheses
                
                parts = re.split(r'\s*\+\s*|\s*/\s*|\s*&\s*|\s+and\s+', base_filter, flags=re.IGNORECASE)
                parts = [p.strip() for p in parts if p.strip()]
                
                if len(parts) == 1:
                    sql_filter = f"\"name\" = '{parts[0]}'"
                else:
                    names_str = ", ".join(f"'{p}'" for p in parts)
                    sql_filter = f"\"name\" IN ({names_str})"
                    
                base_group = root.findGroup("Base Layer")
                base_layer_for_mask = None
                if base_group:
                    for child in base_group.children():
                        if isinstance(child, QgsLayerTreeLayer) and child.layer():
                            base_layer_for_mask = child.layer()
                            base_layer_for_mask.setSubsetString(sql_filter)
                            break
                # Clip Basemap
                basemap_group = root.findGroup("Basemap")
                if basemap_group and base_layer_for_mask:
                    for child in basemap_group.children():
                        if isinstance(child, QgsLayerTreeLayer) and child.layer():
                            raster_layer = child.layer()
                            import processing
                            import tempfile
                            from qgis.core import QgsFeatureRequest, QgsRasterLayer
                            
                            mask_memory_layer = base_layer_for_mask.materialize(QgsFeatureRequest())
                            temp_raster_path = os.path.join(tempfile.gettempdir(), f"{raster_layer.name()}.gpkg")
                            params = {
                                'INPUT': raster_layer,
                                'MASK': mask_memory_layer,
                                'CROP_TO_CROP_EXT': True,
                                'ALPHA_BAND': True,
                                'OPTIONS': 'TILE_FORMAT=PNG_JPEG',
                                'OUTPUT': temp_raster_path
                            }
                            try:
                                res = processing.run("gdal:cliprasterbymasklayer", params)
                                if res and res.get('OUTPUT'):
                                    clipped_path = res['OUTPUT']
                                    
                                    try:
                                        from osgeo import gdal
                                        ds = gdal.Open(clipped_path, gdal.GA_Update)
                                        if ds:
                                            ds.BuildOverviews("NEAREST", [2, 4, 8, 16, 32, 64])
                                            ds = None
                                    except Exception as e:
                                        print(f"GDAL overviews failed: {e}")
                                        
                                    new_raster = QgsRasterLayer(clipped_path, raster_layer.name(), "gdal")
                                    if new_raster.isValid():
                                        temp_project.addMapLayer(new_raster, False)
                                        basemap_group.insertLayer(0, new_raster)
                                        temp_project.removeMapLayer(raster_layer.id())
                            except Exception as e:
                                print(f"Clip failed: {e}")
                            break

            try:
                # Lock non-sample layers in temp_project
                root = temp_project.layerTreeRoot()
                sample_group = root.findGroup("Samples")
                sample_layers = set()
                if sample_group:
                    for child in sample_group.children():
                        if isinstance(child, QgsLayerTreeLayer) and child.layer():
                            sample_layers.add(child.layer().id())

                for layer in temp_project.mapLayers().values():
                    if layer.id() not in sample_layers:
                        try:
                            layer.setCustomProperty("identify/disabled", True)
                            layer.setReadOnly(True)
                        except Exception:
                            pass

                original_addProject = qgis.utils.iface.addProject
                qgis.utils.iface.addProject = lambda p: None
                try:
                    conv = CloudConverter(temp_project, str(target_dir))
                    conv.convert()
                finally:
                    qgis.utils.iface.addProject = original_addProject
                    # Release file locks by clearing temp_project explicitly
                    del conv
                    temp_project.clear()
                    del temp_project
                    gc.collect()

                # Rename attachments to 'attachments.zip'
                attachments = sorted(
                    target_dir.glob("*_attachments.zip"),
                    key=lambda p: p.stat().st_mtime, reverse=True
                )
                if attachments:
                    dest = target_dir / "attachments.zip"
                    try:
                        if dest.exists():
                            dest.unlink()
                        newest = attachments[0]
                        newest.replace(dest)
                        for p in attachments[1:]:
                            p.unlink(missing_ok=True)
                    except Exception:
                        pass

                # Package newest .qgs -> .qgz (then delete .qgs)
                qgs_candidates = sorted(
                    target_dir.glob("*.qgs"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True
                )
                if not qgs_candidates:
                    listing = "\n".join(sorted(p.name for p in target_dir.glob("*")))
                    raise FileNotFoundError("No .qgs produced by converter.\n" + f"Folder contents:\n{listing}")

                produced_qgs = qgs_candidates[0]

                if psu_filter:
                    old_gpkg_name = f"{nos}_{mun}_Selected SSU_{rep}.gpkg"
                    new_gpkg_name = f"{nos}_{mun}_Selected SSU_{rep}_{psu_filter}.gpkg"
                    old_gpkg_path = target_dir / old_gpkg_name
                    if old_gpkg_path.exists():
                        # Retry loop in case Windows is slow releasing the file lock
                        for _ in range(10):
                            try:
                                old_gpkg_path.rename(target_dir / new_gpkg_name)
                                break
                            except PermissionError:
                                time.sleep(0.2)
                                
                        qgs_content = produced_qgs.read_text(encoding="utf-8")
                        qgs_content = qgs_content.replace(old_gpkg_name, new_gpkg_name)
                        produced_qgs.write_text(qgs_content, encoding="utf-8")

                    if ref_extent:
                        import xml.etree.ElementTree as ET
                        try:
                            tree = ET.parse(produced_qgs)
                            root_xml = tree.getroot()
                            mapcanvas = root_xml.find("mapcanvas")
                            if mapcanvas is not None:
                                extent_xml = mapcanvas.find("extent")
                                if extent_xml is None:
                                    extent_xml = ET.SubElement(mapcanvas, "extent")
                                
                                ext = ref_extent
                                ext.scale(1.2)
                                
                                for tag, val in [("xmin", ext.xMinimum()), ("ymin", ext.yMinimum()), ("xmax", ext.xMaximum()), ("ymax", ext.yMaximum())]:
                                    elem = extent_xml.find(tag)
                                    if elem is None:
                                        elem = ET.SubElement(extent_xml, tag)
                                    elem.text = str(val)
                                    
                            tree.write(produced_qgs, encoding="utf-8", xml_declaration=True)
                        except Exception as e:
                            print(f"Failed to patch extent in QGS: {e}")

                qgz_path = target_dir / f"{inner_folder_name}.qgz"
                if qgz_path.exists():
                    qgz_path.unlink()

                with ZipFile(qgz_path, "w", compression=ZIP_DEFLATED) as zf:
                    zf.write(str(produced_qgs), arcname="project.qgs")

                produced_qgs.unlink(missing_ok=True)
                backup = target_dir / (produced_qgs.name + "~")
                backup.unlink(missing_ok=True)

                return qgz_path

            finally:
                pass

        # ---------- If not exporting per PSU ----------
        if reply == QMessageBox.No:
            from PyQt5.QtWidgets import QApplication
            self.genrate.setEnabled(False)
            self.progbar.setValue(50)
            QApplication.processEvents()
            inner_folder = f"{nos}_{mun}_Selected SSU_{rep}"
            try:
                filter_val = single_psu_name if single_psu_only else None
                qgz_path = run_convert(inner_folder, psu_filter=filter_val)
                self.progbar.setValue(100)
                QApplication.processEvents()
                QMessageBox.information(self, "Export Successful",
                                        f"Folder:\n{qgz_path.parent}\n\nProject (.qgz only):\n{qgz_path}")
                # Reset UI
                self.fileWidget.setEnabled(True)
                self.comboxNOS.setEnabled(True)
                self.comboxMun.setEnabled(True)
                self.comboxRep.setEnabled(True)
                self.comboxMun.setCurrentIndex(0)
                self.comboxRep.setCurrentIndex(0)
                self.progbar.setValue(0)
                self.aplqml.setEnabled(False)
                self.genrate.setEnabled(False)
                self.loadbtn.setEnabled(True)
            except Exception as e:
                QMessageBox.critical(self, "Export Failed", str(e))
            return

        # ---------- Export per PSU ----------
        if not layer:
            QMessageBox.critical(self, "Error", "Reference layer 'Selected SSU_Ref' not found.")
            return
        idx = layer.fields().lookupField("PSU_Name")
        if idx == -1:
            QMessageBox.critical(self, "Error", "Field 'PSU_Name' not found in Selected SSU_Ref.")
            return

        psu_names = sorted({self._clean(str(f[idx])) for f in layer.getFeatures() if f[idx] not in (None, "")})
        if not psu_names:
            QMessageBox.critical(self, "Error", "No PSU_Name values found.")
            return

        if single_psu_only:
            selected_psus = [single_psu_name]
        else:
            selected_psus = self.choose_psus(psu_names)
            if not selected_psus:
                return  # user cancelled

        from PyQt5.QtWidgets import QApplication
        self.genrate.setEnabled(False)
        self.progbar.setValue(0)
        QApplication.processEvents()

        success, fail = 0, 0
        errors = []
        total = len(selected_psus)
        for i, psu in enumerate(selected_psus):
            self.progbar.setValue(int((i / total) * 100))
            QApplication.processEvents()
            inner_folder = f"{nos}_{mun}_Selected SSU_{rep}_{psu}"
            try:
                _ = run_convert(inner_folder, psu_filter=psu)
                success += 1
            except Exception as e:
                fail += 1
                errors.append(f"{psu}: {e}")

        self.progbar.setValue(100)
        QApplication.processEvents()
        summary = f"Generated {success} Qfield Projects"

        # Reset UI
        self.fileWidget.setEnabled(True)
        self.comboxNOS.setEnabled(True)
        self.comboxMun.setEnabled(True)
        self.comboxRep.setEnabled(True)
        self.comboxMun.setCurrentIndex(0)
        self.comboxRep.setCurrentIndex(0)
        self.progbar.setValue(0)
        self.aplqml.setEnabled(False)
        self.genrate.setEnabled(False)
        self.loadbtn.setEnabled(True)

        if fail:
            summary += f"\nFailed: {fail}\n" + "\n".join(errors[:10])

        QMessageBox.information(self, "Batch Export Finished", summary)
            
    def choose_psus(self, psu_names):
        """Modal dialog to choose multiple PSU names. Returns a list of selected names."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Choose PSU Name(s)")

        label = QLabel("Select one or more PSU Name:")
        listw = QListWidget()
        listw.addItems(psu_names)
        listw.setSelectionMode(QAbstractItemView.MultiSelection)
        listw.setMinimumWidth(420)
        listw.setMinimumHeight(320)

        btn_ok = QPushButton("Export")
        btn_cancel = QPushButton("Cancel")
        btn_all = QPushButton("Select All")
        btn_clear = QPushButton("Clear")

        def _select_all():
            listw.selectAll()

        def _clear():
            listw.clearSelection()

        def _accept():
            if not listw.selectedItems():
                QMessageBox.information(self, "Nothing selected", "Please select at least one PSU Name.")
                return
            dlg.accept()

        btn_all.clicked.connect(_select_all)
        btn_clear.clicked.connect(_clear)
        btn_ok.clicked.connect(_accept)
        btn_cancel.clicked.connect(dlg.reject)

        # layout
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