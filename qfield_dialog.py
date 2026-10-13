# Developer: TechCraft by Chano
# email: c.dacpano@psa.gov.ph
# GeoFASU_Mod - Apply Style & Generate QField Module

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

FORM_CLASS, _ = uic.loadUiType(os.path.join(os.path.dirname(__file__), 'qfield_dialog.ui'))


class QFieldDialog(QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setupUi(self)
        apply_modern_style(self)
        setup_dialog_logo(self)
        self.plugin_dir = os.path.dirname(__file__)

        self.progbar.setValue(0)
        self.comboxNOS.setPlaceholderText("-- Select Type of Survey --")
        self.comboxMun.setPlaceholderText("-- Select City/Municipality --")
        self.comboxRep.setPlaceholderText("-- Select Replicate Number --")

        # Signals
        self.fileWidget.fileChanged.connect(self.populate_nos_list)
        self.comboxNOS.currentIndexChanged.connect(self.update_mun_list)
        self.comboxMun.currentIndexChanged.connect(self.update_rep_list)
        self.aplqml.clicked.connect(self.apply_styles)
        self.genrate.clicked.connect(self.export_qfield_project)

    def _clean(self, s: str) -> str:
        """Windows-safe filename cleaner."""
        s = (s or "").strip()
        s = re.sub(r'[<>:"/\\|?*]+', "_", s)
        return s.rstrip(" .")

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

    # ---------- Styles ----------
    def apply_styles(self):
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
                    QMessageBox.critical(self, "Error", f"No/Missing Groups/Layer Loaded: '{gname}'. Please load layers first.")
                    self.progbar.setValue(0)
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
            QCoreApplication.processEvents()
            QMessageBox.information(self, "Style Applied", "QML styles successfully applied to project layers.")

        except Exception as e:
            self.progbar.setValue(0)
            QMessageBox.critical(self, "Error", f"Failed to apply styles: {str(e)}")

    # ---------- Export ----------
    def export_qfield_project(self):
        if not HAS_QFIELDSYNC:
            QMessageBox.critical(
                self, "Error",
                "QFieldSync plugin is not installed or enabled. Please install QFieldSync to use this export feature."
            )
            return

        project = QgsProject.instance()

        base_dir = self.fileWidget.filePath()
        if not base_dir:
            QMessageBox.critical(self, "Error", "Please select a Reference Directory.")
            return
        base_path = Path(base_dir)

        nos = self._clean(self.comboxNOS.currentText())
        mun = self._clean(self.comboxMun.currentText())
        rep = self._clean(self.comboxRep.currentText())
        if not all([nos, mun, rep]):
            QMessageBox.critical(self, "Error", "Please ensure Type of Survey, Municipality, and Replicate are selected.")
            return

        # Detect PSU count before asking
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

        if single_psu_only:
            reply = QMessageBox.Yes
        else:
            reply = QMessageBox.question(
                self, "Export by PSU?",
                "Do you want to export separately by PSU name?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )

        try:
            Preferences().set_value("exportDirectory", str(base_path))
        except Exception:
            pass

        def run_convert(inner_folder_name, psu_filter=None, progress_callback=None):
            def set_prog(val):
                if progress_callback:
                    progress_callback(val)
                QCoreApplication.processEvents()

            set_prog(5)
            target_root = base_path / "Package for Qfield" / nos
            target_dir = target_root / inner_folder_name
            target_dir.mkdir(parents=True, exist_ok=True)

            val_root = base_path / "Validation Output" / nos / mun
            val_root.mkdir(parents=True, exist_ok=True)

            temp_proj_path = str(base_path / "geofasu_temp_export.qgz")
            project.write(temp_proj_path)

            temp_project = QgsProject()
            temp_project.read(temp_proj_path)
            temp_project.setFileName(str(target_dir / f"{inner_folder_name}.qgz"))

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
                            except Exception as e:
                                pass
                            break

                sample_group = root.findGroup("Samples")
                sample_layer_name = f"{nos}_{mun}_Selected SSU_{rep}"
                if sample_group:
                    for child in sample_group.children():
                        if child.name() == sample_layer_name and child.layer():
                            child.layer().setSubsetString(f"\"PSU_Name\" = '{psu_filter}'")
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

            set_prog(20)
            cc = CloudConverter(temp_project, str(target_dir))
            cc.convert()
            set_prog(70)

            # Copy validation outputs and zip
            for gpkg_cand in target_dir.glob("*.gpkg"):
                if not any(k in gpkg_cand.name.lower() for k in ["ref", "tracklog", "bdry"]):
                    shutil.copy2(gpkg_cand, val_root / gpkg_cand.name)

            set_prog(85)
            zip_dest = target_root / f"{inner_folder_name}.zip"
            with ZipFile(zip_dest, "w", ZIP_DEFLATED) as zf:
                for file_p in target_dir.rglob("*"):
                    if file_p.is_file():
                        zf.write(file_p, file_p.relative_to(target_root))

            set_prog(100)
            return target_dir

        # Execute export
        if reply == QMessageBox.No:
            self.progbar.setValue(10)
            QCoreApplication.processEvents()
            inner_name = f"{nos}_{mun}_Selected SSU_{rep}"
            try:
                run_convert(inner_name, progress_callback=lambda p: self.progbar.setValue(p))
                self.progbar.setValue(100)
                QMessageBox.information(self, "Export Complete", f"Successfully generated QField project: {inner_name}")
            except Exception as e:
                self.progbar.setValue(0)
                QMessageBox.critical(self, "Export Failed", str(e))
            return

        # Export per PSU
        if not layer:
            QMessageBox.critical(self, "Error", "Reference layer 'Selected SSU_Ref' not found in project.")
            return

        idx = layer.fields().lookupField("PSU_Name")
        if idx == -1:
            QMessageBox.critical(self, "Error", "Field 'PSU_Name' not found in Selected SSU_Ref.")
            return

        psu_names = sorted({self._clean(str(f[idx])) for f in layer.getFeatures() if f[idx] not in (None, "")})
        if not psu_names:
            QMessageBox.critical(self, "Error", "No PSU_Name values found in Reference layer.")
            return

        if single_psu_only:
            selected_psus = [single_psu_name]
        else:
            selected_psus = self.choose_psus(psu_names)
            if not selected_psus:
                return

        self.progbar.setValue(0)
        QCoreApplication.processEvents()

        success, fail = 0, 0
        total = len(selected_psus)
        for i, psu in enumerate(selected_psus):
            def make_cb(index):
                def cb(p):
                    self.progbar.setValue(int(((index + (p / 100)) / total) * 100))
                return cb

            inner_folder = f"{nos}_{mun}_Selected SSU_{rep}_{psu}"
            try:
                _ = run_convert(inner_folder, psu_filter=psu, progress_callback=make_cb(i))
                success += 1
            except Exception:
                fail += 1

        self.progbar.setValue(100)
        QMessageBox.information(
            self, "Export Finished",
            f"Generated {success} QField Project(s)." + (f" ({fail} failed)" if fail else "")
        )

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
