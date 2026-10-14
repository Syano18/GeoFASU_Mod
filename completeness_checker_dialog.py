# Developer: TechCraft by Chano
# email: c.dacpano@psa.gov.ph
# GeoFASU_Mod - Completeness Checker Module

import os
import re
from datetime import datetime
from pathlib import Path

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QMessageBox
from qgis.PyQt.QtCore import Qt, QCoreApplication, QVariant
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsField,
)

try:
    from .style import apply_modern_style, setup_dialog_logo
except (ImportError, ValueError):
    from style import apply_modern_style, setup_dialog_logo

FORM_CLASS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "completeness_checker_dialog.ui")
)


def is_null_or_empty(val):
    """Determines whether an attribute value is Null, empty, or a null-equivalent string."""
    if val is None:
        return True
    if hasattr(val, "isNull") and val.isNull():
        return True
    if type(val).__name__ == "QPyNullVariant":
        return True
    s = str(val).strip()
    return s == "" or s.upper() in ["NULL", "NONE", "NAN"]


def to_int_or_none(val):
    """Converts a value to int if possible (handles int, float strings like '6.0')."""
    if is_null_or_empty(val):
        return None
    s = str(val).strip()
    try:
        f = float(s)
        if f.is_integer():
            return int(f)
    except (ValueError, TypeError):
        pass
    return None


def find_field_name(layer, target_name, alternatives=None):
    """
    Finds field in layer matching target_name or alternatives,
    case-insensitively and ignoring underscores/spaces.
    """
    if not layer or not hasattr(layer, "fields"):
        return None
    field_names = [f.name() for f in layer.fields()]
    if target_name in field_names:
        return target_name

    candidates = [target_name] + (alternatives or [])
    for cand in candidates:
        for f in field_names:
            if f.lower() == cand.lower():
                return f

    def normalize(s):
        return re.sub(r"[\s_]+", "", s).lower()

    for cand in candidates:
        norm_cand = normalize(cand)
        for f in field_names:
            if normalize(f) == norm_cand:
                return f

    return None


class CompletenessCheckerDialog(QDialog, FORM_CLASS):
    def __init__(self, iface=None, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setupUi(self)
        apply_modern_style(self)

        self.progressBar.setValue(0)
        self.updateButton.setEnabled(False)
        self.set_status("READY")

        # Initial layer population
        self.populate_layers()

        # Connect project layer events
        QgsProject.instance().layersAdded.connect(self.populate_layers)
        QgsProject.instance().layersRemoved.connect(self.populate_layers)

        # UI Signals
        self.runButton.clicked.connect(self.run_checker)
        self.updateButton.clicked.connect(self.update_ssu_list)

    def showEvent(self, event):
        self.populate_layers()
        super().showEvent(event)

    def set_status(self, status: str):
        """Styles the status indicator label."""
        if status == "PASSED":
            self.statusLabel.setText("STATUS: PASSED")
            self.statusLabel.setStyleSheet(
                "background-color: #DCFCE7; color: #15803D; font-weight: 700; "
                "font-size: 13px; border: 1.5px solid #22C55E; border-radius: 6px; padding: 4px;"
            )
        elif status == "FAILED":
            self.statusLabel.setText("STATUS: FAILED")
            self.statusLabel.setStyleSheet(
                "background-color: #FEE2E2; color: #B91C1C; font-weight: 700; "
                "font-size: 13px; border: 1.5px solid #EF4444; border-radius: 6px; padding: 4px;"
            )
        else:
            self.statusLabel.setText("STATUS: READY")
            self.statusLabel.setStyleSheet(
                "background-color: #F1F5F9; color: #475569; font-weight: 600; "
                "font-size: 12px; border: 1px solid #CBD5E1; border-radius: 6px; padding: 4px;"
            )

    def log(self, message: str):
        """Appends a line of text to the logs widget."""
        self.logsTextEdit.appendPlainText(message)
        self.logsTextEdit.verticalScrollBar().setValue(
            self.logsTextEdit.verticalScrollBar().maximum()
        )

    def populate_layers(self):
        """Populates Sample SSU and Reference SSU dropdowns from vector layers in QGIS."""
        self.comboxSample.blockSignals(True)
        self.comboxRef.blockSignals(True)

        prev_sample_id = self.comboxSample.currentData()
        prev_ref_id = self.comboxRef.currentData()

        self.comboxSample.clear()
        self.comboxRef.clear()

        vector_layers = [
            lyr
            for lyr in QgsProject.instance().mapLayers().values()
            if isinstance(lyr, QgsVectorLayer) and lyr.isValid()
        ]

        if not vector_layers:
            self.comboxSample.setPlaceholderText("-- No Vector Layers in Project --")
            self.comboxRef.setPlaceholderText("-- No Vector Layers in Project --")
            self.comboxSample.blockSignals(False)
            self.comboxRef.blockSignals(False)
            return

        self.comboxSample.setPlaceholderText("-- Select Sample SSU Layer --")
        self.comboxRef.setPlaceholderText("-- Select Reference SSU Layer --")

        sample_match_idx = -1
        ref_match_idx = -1

        for idx, lyr in enumerate(vector_layers):
            self.comboxSample.addItem(lyr.name(), lyr.id())
            self.comboxRef.addItem(lyr.name(), lyr.id())

            lyr_name_lower = lyr.name().lower()

            # Auto-detection for Sample SSU
            if sample_match_idx == -1:
                if (
                    ("selected ssu" in lyr_name_lower or "sample" in lyr_name_lower)
                    and "ref" not in lyr_name_lower
                ):
                    sample_match_idx = idx

            # Auto-detection for Reference SSU
            if ref_match_idx == -1:
                if "ref" in lyr_name_lower:
                    ref_match_idx = idx

        # Restore previous selection or use auto-detected
        if prev_sample_id:
            idx = self.comboxSample.findData(prev_sample_id)
            if idx != -1:
                self.comboxSample.setCurrentIndex(idx)
            elif sample_match_idx != -1:
                self.comboxSample.setCurrentIndex(sample_match_idx)
        elif sample_match_idx != -1:
            self.comboxSample.setCurrentIndex(sample_match_idx)

        if prev_ref_id:
            idx = self.comboxRef.findData(prev_ref_id)
            if idx != -1:
                self.comboxRef.setCurrentIndex(idx)
            elif ref_match_idx != -1:
                self.comboxRef.setCurrentIndex(ref_match_idx)
        elif ref_match_idx != -1:
            self.comboxRef.setCurrentIndex(ref_match_idx)

        self.comboxSample.blockSignals(False)
        self.comboxRef.blockSignals(False)

    def run_checker(self):
        """Executes completeness validation between Sample SSU and Reference SSU."""
        self.logsTextEdit.clear()
        self.progressBar.setValue(0)
        self.updateButton.setEnabled(False)
        self.set_status("READY")

        sample_id = self.comboxSample.currentData()
        ref_id = self.comboxRef.currentData()

        sample_layer = QgsProject.instance().mapLayer(sample_id) if sample_id else None
        ref_layer = QgsProject.instance().mapLayer(ref_id) if ref_id else None

        if not sample_layer or not sample_layer.isValid():
            QMessageBox.warning(
                self,
                "Missing Layer",
                "Please select a valid Sample SSU layer.",
            )
            return

        if not ref_layer or not ref_layer.isValid():
            QMessageBox.warning(
                self,
                "Missing Layer",
                "Please select a valid Reference SSU layer.",
            )
            return

        if sample_layer.id() == ref_layer.id():
            QMessageBox.warning(
                self,
                "Duplicate Layers Selected",
                "Sample SSU and Reference SSU must be different layers.",
            )
            return

        self.runButton.setEnabled(False)
        self.progressBar.setValue(10)
        QCoreApplication.processEvents()

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log(f"[{now_str}] Starting Completeness Check...")
        self.log(f"• Sample SSU Layer: '{sample_layer.name()}'")
        self.log(f"• Reference SSU Layer: '{ref_layer.name()}'")
        self.log("-" * 55)

        try:
            # 1. Resolve Sample SSU fields
            f_uc = find_field_name(
                sample_layer,
                "Update Codes",
                ["Update_Codes", "update codes", "update_code", "Update Code", "UC"],
            )
            f_uc6 = find_field_name(
                sample_layer,
                "uc_6_ind",
                ["uc6ind", "uc_6_indicator", "UC_6_IND", "uc_6"],
            )

            if not f_uc:
                self.log("ERROR: 'Update Codes' column not found in Sample SSU layer.")
                self.set_status("FAILED")
                QMessageBox.critical(
                    self, "Missing Column", "Could not find 'Update Codes' column in Sample SSU."
                )
                return

            if not f_uc6:
                self.log("WARNING: 'uc_6_ind' column not found in Sample SSU layer.")

            # 2. Resolve Reference SSU fields
            f_sel = find_field_name(
                ref_layer,
                "Selected_SSU",
                ["Selected SSU", "selected_ssu", "selected ssu", "SelectedSSU"],
            )

            if not f_sel:
                self.log("ERROR: 'Selected_SSU' column not found in Reference SSU layer.")
                self.set_status("FAILED")
                QMessageBox.critical(
                    self, "Missing Column", "Could not find 'Selected_SSU' column in Reference SSU."
                )
                return

            # 3. Count Sample SSU
            self.progressBar.setValue(25)
            QCoreApplication.processEvents()

            sample_valid_count = 0
            code_counts = {c: 0 for c in range(7)}
            code_6_skipped = 0

            for feat in sample_layer.getFeatures():
                raw_uc = feat[f_uc]
                uc_int = to_int_or_none(raw_uc)
                if uc_int is not None and 0 <= uc_int <= 6:
                    if uc_int == 6:
                        # uc_6_ind must equal 1
                        raw_uc6 = feat[f_uc6] if f_uc6 else None
                        uc6_int = to_int_or_none(raw_uc6)
                        if uc6_int == 1:
                            sample_valid_count += 1
                            code_counts[6] += 1
                        else:
                            code_6_skipped += 1
                    else:
                        sample_valid_count += 1
                        code_counts[uc_int] += 1

            self.progressBar.setValue(60)
            QCoreApplication.processEvents()

            # 4. Count Reference SSU
            ref_selected_count = 0
            for feat in ref_layer.getFeatures():
                raw_sel = feat[f_sel]
                sel_int = to_int_or_none(raw_sel)
                if sel_int == 1:
                    ref_selected_count += 1

            self.progressBar.setValue(85)
            QCoreApplication.processEvents()

            # Log counting details
            self.log(f"Sample SSU Total Valid Count: {sample_valid_count}")
            self.log(
                f"  └─ Breakdown: Code 0={code_counts[0]}, 1={code_counts[1]}, "
                f"2={code_counts[2]}, 3={code_counts[3]}, 4={code_counts[4]}, "
                f"5={code_counts[5]}, 6={code_counts[6]}"
            )
            if code_6_skipped > 0:
                self.log(f"  └─ Note: {code_6_skipped} record(s) with Update Code 6 had uc_6_ind != 1 (excluded).")

            self.log(f"Reference SSU Total Count (Selected_SSU = 1): {ref_selected_count}")
            self.log("-" * 55)

            # 5. Comparison
            if sample_valid_count == ref_selected_count:
                self.set_status("PASSED")
                self.updateButton.setEnabled(True)
                self.log("RESULT: PASSED ✓")
                self.log("Sample SSU count matches Reference SSU count perfectly.")
                self.log("You can now click 'Update SSU List' to merge missing reference records if needed.")
                QMessageBox.information(
                    self,
                    "Completeness Check Passed",
                    f"Check PASSED!\n\nSample SSU Count: {sample_valid_count}\n"
                    f"Reference SSU Count: {ref_selected_count}\n\n"
                    "The 'Update SSU List' button is now enabled.",
                )
            else:
                self.set_status("FAILED")
                self.updateButton.setEnabled(False)
                diff = sample_valid_count - ref_selected_count
                diff_desc = f"{abs(diff)} more in Sample" if diff > 0 else f"{abs(diff)} more in Reference"
                self.log("RESULT: FAILED ✗")
                self.log(f"Counts do not match! Difference: {abs(diff)} ({diff_desc}).")
                self.log("Please review your surveyed records and reference layer before proceeding.")
                QMessageBox.warning(
                    self,
                    "Completeness Check Failed",
                    f"Check FAILED!\n\nSample SSU Count: {sample_valid_count}\n"
                    f"Reference SSU Count: {ref_selected_count}\n"
                    f"Difference: {abs(diff)} ({diff_desc})\n\n"
                    "Counts must be equal to enable updating the SSU list.",
                )

            self.progressBar.setValue(100)

        except Exception as e:
            self.log(f"EXCEPTION: {e}")
            self.set_status("FAILED")
            QMessageBox.critical(self, "Error", f"An unexpected error occurred during check:\n{e}")
        finally:
            self.runButton.setEnabled(True)

    def update_ssu_list(self):
        """Merges missing records from Reference SSU into Sample SSU using (BSN, HUSN, HSN)."""
        sample_id = self.comboxSample.currentData()
        ref_id = self.comboxRef.currentData()

        sample_layer = QgsProject.instance().mapLayer(sample_id) if sample_id else None
        ref_layer = QgsProject.instance().mapLayer(ref_id) if ref_id else None

        if not sample_layer or not sample_layer.isValid() or not ref_layer or not ref_layer.isValid():
            QMessageBox.warning(self, "Invalid Layers", "Please ensure both layers are valid.")
            return

        # Resolve BSN, HUSN, HSN in both layers
        s_bsn = find_field_name(sample_layer, "BSN", ["bsn", "BS_No"])
        s_husn = find_field_name(sample_layer, "HUSN", ["husn", "HU_SN"])
        s_hsn = find_field_name(sample_layer, "HSN", ["hsn"])

        r_bsn = find_field_name(ref_layer, "BSN", ["bsn", "BS_No"])
        r_husn = find_field_name(ref_layer, "HUSN", ["husn", "HU_SN"])
        r_hsn = find_field_name(ref_layer, "HSN", ["hsn"])

        if not all([s_bsn, s_husn, s_hsn]):
            missing = [c for c, f in [("BSN", s_bsn), ("HUSN", s_husn), ("HSN", s_hsn)] if not f]
            QMessageBox.critical(
                self, "Missing Key Column", f"Sample SSU layer is missing: {', '.join(missing)}"
            )
            return

        if not all([r_bsn, r_husn, r_hsn]):
            missing = [c for c, f in [("BSN", r_bsn), ("HUSN", r_husn), ("HSN", r_hsn)] if not f]
            QMessageBox.critical(
                self, "Missing Key Column", f"Reference SSU layer is missing: {', '.join(missing)}"
            )
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Update SSU List",
            f"Are you sure you want to copy missing records from '{ref_layer.name()}' "
            f"into '{sample_layer.name()}' based on (BSN, HUSN, HSN)?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if confirm != QMessageBox.Yes:
            return

        self.updateButton.setEnabled(False)
        self.progressBar.setValue(10)
        QCoreApplication.processEvents()

        try:
            # 1. Collect all keys currently present in Sample SSU
            sample_keys = set()
            for feat in sample_layer.getFeatures():
                b = str(feat[s_bsn]).strip() if not is_null_or_empty(feat[s_bsn]) else ""
                hu = str(feat[s_husn]).strip() if not is_null_or_empty(feat[s_husn]) else ""
                h = str(feat[s_hsn]).strip() if not is_null_or_empty(feat[s_hsn]) else ""
                if b or hu or h:
                    sample_keys.add((b, hu, h))

            self.progressBar.setValue(30)
            QCoreApplication.processEvents()

            # 2. Identify missing features from Reference SSU
            features_to_add = []
            sample_fields = sample_layer.fields()

            # Map sample field name -> ref field name
            field_map = {}
            for sf in sample_fields:
                rf = find_field_name(ref_layer, sf.name())
                if rf:
                    field_map[sf.name()] = rf

            missing_records_log = []

            for r_feat in ref_layer.getFeatures():
                b = str(r_feat[r_bsn]).strip() if not is_null_or_empty(r_feat[r_bsn]) else ""
                hu = str(r_feat[r_husn]).strip() if not is_null_or_empty(r_feat[r_husn]) else ""
                h = str(r_feat[r_hsn]).strip() if not is_null_or_empty(r_feat[r_hsn]) else ""
                key = (b, hu, h)

                if key not in sample_keys:
                    new_feat = QgsFeature(sample_fields)
                    if r_feat.hasGeometry():
                        new_feat.setGeometry(r_feat.geometry())

                    for s_col, r_col in field_map.items():
                        new_feat[s_col] = r_feat[r_col]

                    features_to_add.append(new_feat)
                    missing_records_log.append(f"BSN={b}, HUSN={hu}, HSN={h}")
                    sample_keys.add(key)  # prevent duplicate additions if ref has dupes

            self.progressBar.setValue(70)
            QCoreApplication.processEvents()

            if not features_to_add:
                self.log("Update SSU List: All records from Reference SSU are already present in Sample SSU (0 added).")
                QMessageBox.information(
                    self,
                    "No Missing Records",
                    "All records in the Reference SSU layer are already present in the Sample SSU layer.\nNo changes were needed.",
                )
                self.progressBar.setValue(100)
                return

            # 3. Add features to sample layer
            success = sample_layer.dataProvider().addFeatures(features_to_add)

            if success:
                sample_layer.updateExtents()
                sample_layer.triggerRepaint()
                if self.iface and hasattr(self.iface, "mapCanvas") and self.iface.mapCanvas():
                    self.iface.mapCanvas().refresh()

                self.log(f"Successfully copied {len(features_to_add)} missing record(s) into '{sample_layer.name()}':")
                for item in missing_records_log[:15]:
                    self.log(f"  + Added: {item}")
                if len(missing_records_log) > 15:
                    self.log(f"  + ... and {len(missing_records_log) - 15} more records.")

                self.progressBar.setValue(100)
                QMessageBox.information(
                    self,
                    "Update SSU List Complete",
                    f"Successfully copied {len(features_to_add)} missing record(s) from '{ref_layer.name()}' "
                    f"into '{sample_layer.name()}'.",
                )
            else:
                self.log("ERROR: dataProvider().addFeatures() returned False.")
                QMessageBox.critical(
                    self, "Update Failed", "Failed to insert features into Sample SSU layer."
                )

        except Exception as e:
            self.log(f"EXCEPTION during update: {e}")
            QMessageBox.critical(self, "Error", f"Error updating SSU list:\n{e}")
        finally:
            self.updateButton.setEnabled(False)
