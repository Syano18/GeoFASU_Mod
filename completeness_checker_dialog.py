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
from qgis.gui import QgsFileWidget
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsField,
    QgsVectorFileWriter,
    QgsWkbTypes,
    QgsMarkerSymbol,
    QgsFillSymbol,
    QgsLineSymbol,
    QgsSingleSymbolRenderer,
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


def is_selected_ssu_1(val):
    """
    Checks if a Selected_SSU value represents 1
    (handles int 1, float 1.0, string '1', '1 - Sample SSU', etc.).
    """
    if is_null_or_empty(val):
        return False
    v_int = to_int_or_none(val)
    if v_int == 1:
        return True
    s = str(val).strip()
    if s == "1":
        return True
    if s.startswith("1") and len(s) > 1 and not s[1].isdigit():
        return True
    return False


def apply_error_symbology(layer):
    """Applies a distinct red styling to the error temporary layer."""
    if not layer or not layer.isSpatial():
        return
    geom_type = layer.geometryType()
    if geom_type == QgsWkbTypes.PointGeometry:
        symbol = QgsMarkerSymbol.createSimple(
            {
                "name": "circle",
                "color": "#EF4444",
                "color_border": "#7F1D1D",
                "size": "4.0",
                "outline_width": "0.8",
            }
        )
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    elif geom_type == QgsWkbTypes.PolygonGeometry:
        symbol = QgsFillSymbol.createSimple(
            {
                "color": "239,68,68,80",
                "color_border": "#DC2626",
                "outline_width": "0.8",
                "outline_style": "solid",
            }
        )
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    elif geom_type == QgsWkbTypes.LineGeometry:
        symbol = QgsLineSymbol.createSimple(
            {
                "color": "#DC2626",
                "width": "1.0",
            }
        )
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))


class CompletenessCheckerDialog(QDialog, FORM_CLASS):
    def __init__(self, iface=None, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setupUi(self)
        apply_modern_style(self)

        self.progressBar.setValue(0)
        self.updateButton.setEnabled(False)
        self.set_status("READY")

        # Default Output Directory
        default_dir = r"C:\PSA-GIS\GeoFASU\Kalinga\Project files"
        if hasattr(self, "outputDirWidget"):
            self.outputDirWidget.setStorageMode(QgsFileWidget.GetDirectory)
            self.outputDirWidget.setFilePath(default_dir)

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

    def populate_layers(self, reset_selection=False):
        """Populates Sample SSU and Reference SSU dropdowns from vector layers in QGIS."""
        self.comboxSample.blockSignals(True)
        self.comboxRef.blockSignals(True)

        prev_sample_id = None if reset_selection else self.comboxSample.currentData()
        prev_ref_id = None if reset_selection else self.comboxRef.currentData()

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

        if reset_selection:
            self.comboxSample.setCurrentIndex(-1)
            self.comboxRef.setCurrentIndex(-1)
        else:
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
            self.progressBar.setValue(0)
            return

        if not ref_layer or not ref_layer.isValid():
            QMessageBox.warning(
                self,
                "Missing Layer",
                "Please select a valid Reference SSU layer.",
            )
            self.progressBar.setValue(0)
            return

        if sample_layer.id() == ref_layer.id():
            QMessageBox.warning(
                self,
                "Duplicate Layers Selected",
                "Sample SSU and Reference SSU must be different layers.",
            )
            self.progressBar.setValue(0)
            return

        self.runButton.setEnabled(False)
        self.progressBar.setValue(10)
        QCoreApplication.processEvents()

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log(f"[{now_str}] Starting Completeness Check...")
        self.log(f"• Sample SSU Layer: '{sample_layer.name()}'")
        self.log(f"• Reference SSU Layer: '{ref_layer.name()}'")
        out_dir = (
            self.outputDirWidget.filePath().strip()
            if hasattr(self, "outputDirWidget")
            else ""
        )
        if out_dir:
            self.log(f"• Output Folder: '{out_dir}'")
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
                self.progressBar.setValue(0)
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
                self.progressBar.setValue(0)
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
            self.progressBar.setValue(100)
            QCoreApplication.processEvents()

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
                self.progressBar.setValue(0)
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
                self.progressBar.setValue(0)

        except Exception as e:
            self.log(f"EXCEPTION: {e}")
            self.set_status("FAILED")
            QMessageBox.critical(self, "Error", f"An unexpected error occurred during check:\n{e}")
            self.progressBar.setValue(0)
        finally:
            self.runButton.setEnabled(True)
            self.progressBar.setValue(0)

    def resolve_survey_and_mun(self, sample_layer, ref_layer=None, base_out_dir=None):
        """
        Resolves the Name of Survey and City/Mun Name from:
        1. Layer source paths of Sample SSU and Reference SSU
        2. Feature attributes (Mun_name, Round, Year, Survey)
        3. Layer names (f"{nos}_{mun}_Selected SSU_{rep}")
        4. Existing directories in base_out_dir
        """
        nos = None
        mun = None

        # 1. Check feature attributes for Municipality
        f_mun = find_field_name(
            sample_layer,
            "Mun_name",
            ["mun_name", "MUN_NAME", "City_Mun", "Municipality", "MUN", "mun"],
        )
        if f_mun:
            for feat in sample_layer.getFeatures():
                v = feat[f_mun]
                if not is_null_or_empty(v):
                    mun = str(v).strip()
                    break

        if not mun and ref_layer:
            f_ref_mun = find_field_name(
                ref_layer,
                "Mun_name",
                ["mun_name", "MUN_NAME", "City_Mun", "Municipality", "MUN", "mun"],
            )
            if f_ref_mun:
                for feat in ref_layer.getFeatures():
                    v = feat[f_ref_mun]
                    if not is_null_or_empty(v):
                        mun = str(v).strip()
                        break

        # 2. Check source paths of sample_layer and ref_layer
        sources = []
        if sample_layer:
            sources.append(sample_layer.source().split("|")[0])
        if ref_layer:
            sources.append(ref_layer.source().split("|")[0])

        markers = [
            "Projects",
            "Validation Output",
            "Validation Ouput",
            "From Tablet",
            "Samples",
            "Excel",
            "Filepinas",
        ]
        for src in sources:
            if not src:
                continue
            norm_src = os.path.normpath(src)
            parts = [p for p in norm_src.split(os.sep) if p]
            for marker in markers:
                if marker in parts:
                    idx = parts.index(marker)
                    if not nos and idx + 1 < len(parts):
                        cand_nos = parts[idx + 1]
                        if not cand_nos.lower().endswith(".gpkg"):
                            nos = cand_nos
                    if not mun and idx + 2 < len(parts):
                        cand_mun = parts[idx + 2]
                        if not cand_mun.lower().endswith(".gpkg"):
                            mun = cand_mun
                    break
            if nos and mun:
                break

        # 3. Check layer name parsing: {nos}_{mun}_Selected SSU_{rep}
        names_to_check = []
        if sample_layer:
            names_to_check.append(sample_layer.name())
        if ref_layer:
            names_to_check.append(ref_layer.name())

        for lyr_name in names_to_check:
            m_ssu = re.search(
                r"^(.*?)_(?:Selected SSU|Selected_SSU|SelectedSSU)",
                lyr_name,
                re.IGNORECASE,
            )
            if m_ssu:
                prefix = m_ssu.group(1).strip()
                if mun and prefix.lower().endswith(mun.lower()):
                    cand_nos = prefix[: -len(mun)].rstrip(" _-")
                    if cand_nos and not nos:
                        nos = cand_nos
                elif not nos and not mun:
                    if "_" in prefix:
                        p_parts = prefix.rsplit("_", 1)
                        if not nos:
                            nos = p_parts[0]
                        if not mun:
                            mun = p_parts[1]
            if nos and mun:
                break

        # 4. Check existing directories in base_out_dir
        if base_out_dir and (not nos or not mun):
            for sub in ["Validation Output", "Validation Ouput", "Projects"]:
                check_dir = os.path.join(base_out_dir, sub)
                if os.path.isdir(check_dir):
                    existing_surveys = [
                        d
                        for d in os.listdir(check_dir)
                        if os.path.isdir(os.path.join(check_dir, d))
                    ]
                    if not nos:
                        for s_dir in existing_surveys:
                            for chk in [
                                sample_layer.name() if sample_layer else "",
                                sources[0] if sources else "",
                            ]:
                                if s_dir.lower() in chk.lower():
                                    nos = s_dir
                                    break
                            if nos:
                                break
                    if nos:
                        survey_dir = os.path.join(check_dir, nos)
                        if os.path.isdir(survey_dir):
                            existing_muns = [
                                d
                                for d in os.listdir(survey_dir)
                                if os.path.isdir(os.path.join(survey_dir, d))
                            ]
                            if not mun:
                                for m_dir in existing_muns:
                                    for chk in [
                                        sample_layer.name() if sample_layer else "",
                                        sources[0] if sources else "",
                                    ]:
                                        if m_dir.lower() in chk.lower():
                                            mun = m_dir
                                            break
                                    if mun:
                                        break

        # 5. Fallback defaults if still unresolved
        if not nos:
            if sample_layer:
                m = re.search(
                    r"^(.*?)_(?:Selected SSU|Selected_SSU|SelectedSSU)",
                    sample_layer.name(),
                    re.IGNORECASE,
                )
                if m:
                    nos = m.group(1).strip()
            if not nos:
                nos = "Survey"
        if not mun:
            mun = "Municipality"

        return nos, mun

    def update_ssu_list(self):
        """
        Merges missing records from Reference SSU into Sample SSU using (BSN, HUSN, HSN),
        validates that all records with Selected_SSU == 1 have valid Update Codes,
        generates an error layer if any errors exist, or saves the merged layer to
        <Output Folder>/Validation Output/<Name of Survey>/<City/Mun Name>/<filename>.gpkg.
        """
        sample_id = self.comboxSample.currentData()
        ref_id = self.comboxRef.currentData()

        sample_layer = QgsProject.instance().mapLayer(sample_id) if sample_id else None
        ref_layer = QgsProject.instance().mapLayer(ref_id) if ref_id else None

        if not sample_layer or not sample_layer.isValid() or not ref_layer or not ref_layer.isValid():
            QMessageBox.warning(self, "Invalid Layers", "Please ensure both layers are valid.")
            self.progressBar.setValue(0)
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
            self.progressBar.setValue(0)
            return

        if not all([r_bsn, r_husn, r_hsn]):
            missing = [c for c, f in [("BSN", r_bsn), ("HUSN", r_husn), ("HSN", r_hsn)] if not f]
            QMessageBox.critical(
                self, "Missing Key Column", f"Reference SSU layer is missing: {', '.join(missing)}"
            )
            self.progressBar.setValue(0)
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Update SSU List",
            f"Are you sure you want to merge missing records from '{ref_layer.name()}' "
            f"into '{sample_layer.name()}' and validate before saving?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if confirm != QMessageBox.Yes:
            self.progressBar.setValue(0)
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

            self.progressBar.setValue(50)
            QCoreApplication.processEvents()

            # 3. Add missing features into sample layer if any
            if features_to_add:
                success = sample_layer.dataProvider().addFeatures(features_to_add)
                if not success:
                    self.log("ERROR: dataProvider().addFeatures() returned False.")
                    QMessageBox.critical(
                        self, "Update Failed", "Failed to insert features into Sample SSU layer."
                    )
                    self.progressBar.setValue(0)
                    return

                sample_layer.updateExtents()
                sample_layer.triggerRepaint()
                if self.iface and hasattr(self.iface, "mapCanvas") and self.iface.mapCanvas():
                    self.iface.mapCanvas().refresh()

                self.log(
                    f"Successfully copied {len(features_to_add)} missing record(s) into '{sample_layer.name()}':"
                )
                for item in missing_records_log[:10]:
                    self.log(f"  + Added: {item}")
                if len(missing_records_log) > 10:
                    self.log(f"  + ... and {len(missing_records_log) - 10} more records.")
            else:
                self.log(
                    "Update SSU List: All records from Reference SSU are already present in Sample SSU (0 new records to add)."
                )

            # 4. PRE-SAVE VALIDATION on merged layer
            self.progressBar.setValue(70)
            QCoreApplication.processEvents()

            self.log("-" * 55)
            self.log("Running Pre-Save Validation on merged layer...")

            f_sel = find_field_name(
                sample_layer,
                "Selected_SSU",
                ["Selected SSU", "selected_ssu", "SelectedSSU"],
            )
            f_uc = find_field_name(
                sample_layer,
                "Update Codes",
                [
                    "Updates_Codes",
                    "Update_Codes",
                    "Updates Codes",
                    "Update Codes",
                    "update codes",
                    "updates codes",
                    "update_code",
                    "UC",
                ],
            )

            if not f_sel:
                self.log("ERROR: 'Selected_SSU' column not found in merged Sample SSU layer.")
                QMessageBox.critical(
                    self,
                    "Missing Column",
                    "Could not find 'Selected_SSU' column in Sample SSU layer.",
                )
                self.progressBar.setValue(0)
                return

            if not f_uc:
                self.log("ERROR: 'Update Codes' column not found in merged Sample SSU layer.")
                QMessageBox.critical(
                    self,
                    "Missing Column",
                    "Could not find 'Update Codes' column in Sample SSU layer.",
                )
                self.progressBar.setValue(0)
                return

            layer_errors = []
            selected_1_count = 0

            for feat in sample_layer.getFeatures():
                raw_sel = feat[f_sel]
                if is_selected_ssu_1(raw_sel):
                    selected_1_count += 1
                    raw_uc = feat[f_uc]
                    if is_null_or_empty(raw_uc):
                        layer_errors.append(
                            (feat, "Selected_SSU is 1 but Update Codes is missing/null")
                        )

            # 5. Handle Errors vs Success
            if layer_errors:
                # Create temporary error layer
                temp_name = f"Errors_{sample_layer.name()}"
                crs_auth = sample_layer.crs().authid()
                if sample_layer.isSpatial():
                    wkb_type_str = QgsWkbTypes.displayString(sample_layer.wkbType())
                    uri = f"{wkb_type_str}?crs={crs_auth}"
                else:
                    uri = "none"

                # Remove existing layer with same name if any
                for old_id, old_lyr in list(QgsProject.instance().mapLayers().items()):
                    if old_lyr.name() == temp_name:
                        QgsProject.instance().removeMapLayer(old_id)

                temp_layer = QgsVectorLayer(uri, temp_name, "memory")
                t_pr = temp_layer.dataProvider()
                t_pr.addAttributes(sample_layer.fields())

                try:
                    from qgis.PyQt.QtCore import QMetaType
                    err_field = QgsField("Validation_Errors", QMetaType.Type.QString)
                except Exception:
                    err_field = QgsField("Validation_Errors", QVariant.String)

                t_pr.addAttributes([err_field])
                temp_layer.updateFields()

                new_err_feats = []
                for e_feat, e_reason in layer_errors:
                    nf = QgsFeature(temp_layer.fields())
                    if sample_layer.isSpatial() and e_feat.hasGeometry():
                        nf.setGeometry(e_feat.geometry())
                    attrs = e_feat.attributes()
                    attrs.append(e_reason)
                    nf.setAttributes(attrs)
                    new_err_feats.append(nf)

                t_pr.addFeatures(new_err_feats)
                temp_layer.updateExtents()

                apply_error_symbology(temp_layer)
                QgsProject.instance().addMapLayer(temp_layer)

                if hasattr(self, "iface") and self.iface:
                    self.iface.setActiveLayer(temp_layer)
                    if (
                        temp_layer.isSpatial()
                        and temp_layer.featureCount() > 0
                        and self.iface.mapCanvas()
                    ):
                        self.iface.mapCanvas().setExtent(temp_layer.extent())
                        self.iface.mapCanvas().refresh()

                self.log(
                    f"VALIDATION ERROR: Found {len(layer_errors)} record(s) where Selected_SSU = 1 "
                    f"but Update Codes is missing/null!"
                )
                self.log(f"Temporary error layer created: '{temp_name}'")
                self.log("Error Records List:")
                for idx, (e_feat, e_reason) in enumerate(layer_errors, 1):
                    b = str(e_feat[s_bsn]).strip() if s_bsn and not is_null_or_empty(e_feat[s_bsn]) else "-"
                    hu = str(e_feat[s_husn]).strip() if s_husn and not is_null_or_empty(e_feat[s_husn]) else "-"
                    h = str(e_feat[s_hsn]).strip() if s_hsn and not is_null_or_empty(e_feat[s_hsn]) else "-"
                    self.log(f"  [{idx}] BSN={b}, HUSN={hu}, HSN={h} (FID={e_feat.id()}) → {e_reason}")
                self.log("-" * 55)
                self.log("Saving aborted. Please resolve the missing Update Codes in the error layer.")

                QMessageBox.warning(
                    self,
                    "Validation Errors Found",
                    f"Pre-save Validation FAILED!\n\n"
                    f"Found {len(layer_errors)} record(s) where Selected_SSU = 1 but Update Codes is missing.\n\n"
                    f"A temporary layer '{temp_name}' has been created in QGIS with the error records, "
                    f"and the error details are listed in the Logs.\n\n"
                    f"The .gpkg file was NOT saved.",
                )
                self.progressBar.setValue(0)
                return

            # No errors - Save to Validation Output/Name of Survey/City/Mun Name
            self.progressBar.setValue(85)
            QCoreApplication.processEvents()

            self.log(
                f"PRE-SAVE VALIDATION PASSED ✓ (All {selected_1_count} records with Selected_SSU = 1 "
                f"have valid Update Codes)."
            )

            base_out_dir = (
                self.outputDirWidget.filePath().strip()
                if hasattr(self, "outputDirWidget")
                else ""
            )
            if not base_out_dir:
                base_out_dir = r"C:\PSA-GIS\GeoFASU\Kalinga\Project files"

            nos, mun = self.resolve_survey_and_mun(sample_layer, ref_layer, base_out_dir)

            val_folder_name = "Validation Output"
            if os.path.isdir(os.path.join(base_out_dir, "Validation Ouput")) and not os.path.isdir(
                os.path.join(base_out_dir, "Validation Output")
            ):
                val_folder_name = "Validation Ouput"

            target_folder = os.path.join(base_out_dir, val_folder_name, nos, mun)
            os.makedirs(target_folder, exist_ok=True)

            layer_name = sample_layer.name()
            out_file_name = (
                f"{layer_name}.gpkg"
                if not layer_name.lower().endswith(".gpkg")
                else layer_name
            )
            out_gpkg_path = os.path.join(target_folder, out_file_name)
            source_path = sample_layer.source().split("|")[0]

            if os.path.exists(source_path) and os.path.abspath(source_path) == os.path.abspath(out_gpkg_path):
                self.log(f"GeoPackage updated in-place at:\n  {out_gpkg_path}")
            else:
                options = QgsVectorFileWriter.SaveVectorOptions()
                options.driverName = "GPKG"
                options.fileEncoding = "UTF-8"
                if hasattr(QgsVectorFileWriter, "CreateOrOverwriteFile"):
                    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile
                write_res = QgsVectorFileWriter.writeAsVectorFormatV3(
                    sample_layer,
                    out_gpkg_path,
                    QgsProject.instance().transformContext(),
                    options,
                )
                res = write_res[0] if isinstance(write_res, tuple) else write_res
                err_str = (
                    write_res[3]
                    if (isinstance(write_res, tuple) and len(write_res) > 3)
                    else (
                        write_res[1]
                        if (isinstance(write_res, tuple) and len(write_res) > 1)
                        else ""
                    )
                )
                if res == QgsVectorFileWriter.NoError or res == 0:
                    self.log(f"Exported merged GeoPackage to Validation Output:\n  {out_gpkg_path}")
                else:
                    self.log(f"ERROR: Failed to export GeoPackage: {err_str}")
                    QMessageBox.critical(
                        self,
                        "Export Error",
                        f"Failed to write GeoPackage file to:\n{out_gpkg_path}\n\nError: {err_str}",
                    )
                    self.progressBar.setValue(0)
                    return

            self.progressBar.setValue(100)
            msg = (
                f"Update SSU List completed successfully!\n\n"
                f"• Pre-save Validation: PASSED ({selected_1_count} records validated)\n"
            )
            if len(features_to_add) > 0:
                msg += f"• Missing Records Copied: {len(features_to_add)}\n\n"
            else:
                msg += "• Missing Records Copied: 0 (All reference records were already present)\n\n"
            msg += f"Saved to:\n{out_gpkg_path}"

            QMessageBox.information(self, "Update SSU List Complete", msg)
            self.progressBar.setValue(0)

        except Exception as e:
            self.log(f"EXCEPTION during update: {e}")
            QMessageBox.critical(self, "Error", f"Error updating SSU list:\n{e}")
            self.progressBar.setValue(0)
        finally:
            self.updateButton.setEnabled(False)
            self.progressBar.setValue(0)

    def reset_fields(self):
        """Resets all input fields, logs, status, and progress bar to default values."""
        default_dir = r"C:\PSA-GIS\GeoFASU\Kalinga\Project files"
        if hasattr(self, "outputDirWidget"):
            self.outputDirWidget.setFilePath(default_dir)
        self.populate_layers(reset_selection=True)
        self.logsTextEdit.clear()
        self.set_status("READY")
        self.runButton.setEnabled(True)
        self.updateButton.setEnabled(False)
        self.progressBar.setValue(0)

    def closeEvent(self, event):
        """Clean close event, resets progress bar and all fields."""
        self.reset_fields()
        event.accept()

    def reject(self):
        """Clean reject event, resets progress bar and all fields."""
        self.reset_fields()
        super().reject()
