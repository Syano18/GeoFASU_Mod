# Developer: TechCraft by Chano
# email: c.dacpano@psa.gov.ph
# GeoFASU_Mod - Checker Module

import os
import re
from pathlib import Path
from collections import Counter

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QMessageBox
from qgis.PyQt.QtCore import Qt, QCoreApplication, QVariant
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsField,
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
    os.path.join(os.path.dirname(__file__), "checker_dialog.ui")
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


def is_update_code_5(val):
    """Determines if an Update Codes value represents 5 (as integer, float, or string)."""
    if is_null_or_empty(val):
        return False
    s = str(val).strip()
    try:
        if float(s) == 5.0:
            return True
    except (ValueError, TypeError):
        pass
    return s == "5"


def find_field_name(layer, target_name, alternatives=None):
    """
    Finds field in layer matching target_name or alternatives,
    case-insensitively and ignoring underscores/spaces.
    """
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


def apply_error_symbology(layer):
    """Applies a distinct red styling to the error temporary layer."""
    if not layer.isSpatial():
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


class CheckerDialog(QDialog, FORM_CLASS):
    def __init__(self, iface=None, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setupUi(self)
        apply_modern_style(self)
        setup_dialog_logo(self)

        self.closeButton.setProperty("secondary", True)
        self.progressBar.setValue(0)
        self.comboxSample.setPlaceholderText("-- Select Sample SSU Layer --")
        self.comboxRef.setPlaceholderText("-- Select Reference SSU Layer --")

        # Initial population of project layers
        self.populate_layers()

        # Keep dropdowns in sync if project layers change
        QgsProject.instance().layersAdded.connect(self.populate_layers)
        QgsProject.instance().layersRemoved.connect(self.populate_layers)

        # Signal connections
        self.runButton.clicked.connect(self.run_checker)
        self.closeButton.clicked.connect(self.close)

    def showEvent(self, event):
        """Refreshes layer list when dialog is shown."""
        self.populate_layers()
        super().showEvent(event)

    def populate_layers(self):
        """Populates Sample SSU and Reference SSU dropdowns from vector layers in QGIS."""
        self.comboxSample.blockSignals(True)
        self.comboxRef.blockSignals(True)

        prev_sample_id = self.comboxSample.currentData()
        prev_ref_id = self.comboxRef.currentData()

        self.comboxSample.clear()
        self.comboxRef.clear()

        # Get all valid vector layers in project
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

        # Restore previous selection if still available, otherwise use detected defaults
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
        """Executes validation on Sample SSU and prepares for Reference SSU cross-validation."""
        sample_layer_id = self.comboxSample.currentData()
        sample_layer = QgsProject.instance().mapLayer(sample_layer_id) if sample_layer_id else None

        if not sample_layer or not sample_layer.isValid():
            QMessageBox.warning(
                self,
                "Missing Sample SSU",
                "Please select a valid Sample SSU layer from the dropdown list.",
            )
            return

        ref_layer_id = self.comboxRef.currentData()
        ref_layer = QgsProject.instance().mapLayer(ref_layer_id) if ref_layer_id else None

        self.runButton.setEnabled(False)
        self.progressBar.setValue(5)
        QCoreApplication.processEvents()

        try:
            feature_count = sample_layer.featureCount()

            # Resolve column names in Sample SSU
            f_bsn = find_field_name(sample_layer, "BSN", ["bsn", "BS_No"])
            f_husn = find_field_name(sample_layer, "HUSN", ["husn", "HU_SN"])
            f_hsn = find_field_name(sample_layer, "HSN", ["hsn"])
            f_uc = find_field_name(
                sample_layer,
                "Update Codes",
                ["Update_Codes", "update codes", "update_code", "Update Code", "UC"],
            )
            f_nhhhead = find_field_name(
                sample_layer, "n_hhhead", ["n_hh_head", "nhhhead", "n_head", "new_hhhead"]
            )
            f_nhsn = find_field_name(sample_layer, "n_hsn", ["nhsn", "new_hsn"])
            f_mucind = find_field_name(sample_layer, "m_uc_ind", ["mucind", "m_uc", "muc_ind"])

            # Check if required core columns are present
            missing_core = []
            if not f_bsn:
                missing_core.append("BSN")
            if not f_husn:
                missing_core.append("HUSN")
            if not f_hsn:
                missing_core.append("HSN")
            if not f_uc:
                missing_core.append("Update Codes")

            if missing_core:
                QMessageBox.warning(
                    self,
                    "Missing Columns",
                    f"Sample SSU layer '{sample_layer.name()}' is missing required column(s):\n"
                    f"{', '.join(missing_core)}.",
                )
                return

            self.progressBar.setValue(15)
            QCoreApplication.processEvents()

            # Pass 1: Build frequency map for (BSN, HUSN, HSN) to detect duplicate entries
            bsn_husn_hsn_counts = Counter()
            for feat in sample_layer.getFeatures():
                bsn_val = feat[f_bsn]
                husn_val = feat[f_husn]
                hsn_val = feat[f_hsn]
                if (
                    not is_null_or_empty(bsn_val)
                    and not is_null_or_empty(husn_val)
                    and not is_null_or_empty(hsn_val)
                ):
                    key = (str(bsn_val).strip(), str(husn_val).strip(), str(hsn_val).strip())
                    bsn_husn_hsn_counts[key] += 1

            self.progressBar.setValue(30)
            QCoreApplication.processEvents()

            # Pass 2: Feature-level validation
            layer_errors = []
            processed_count = 0

            for feat in sample_layer.getFeatures():
                reasons = []

                # 1. BSN, HUSN, HSN must not be null
                if is_null_or_empty(feat[f_bsn]):
                    reasons.append("BSN is Null")
                if is_null_or_empty(feat[f_husn]):
                    reasons.append("HUSN is Null")
                if is_null_or_empty(feat[f_hsn]):
                    reasons.append("HSN is Null")

                # 2. Check for duplicate entries based on (BSN, HUSN, HSN)
                if (
                    not is_null_or_empty(feat[f_bsn])
                    and not is_null_or_empty(feat[f_husn])
                    and not is_null_or_empty(feat[f_hsn])
                ):
                    key = (str(feat[f_bsn]).strip(), str(feat[f_husn]).strip(), str(feat[f_hsn]).strip())
                    dup_count = bsn_husn_hsn_counts.get(key, 0)
                    if dup_count > 1:
                        reasons.append(
                            f"Duplicate entry: BSN={key[0]}, HUSN={key[1]}, HSN={key[2]} (appears {dup_count} times)"
                        )

                # 3. Update Codes must not be null
                if is_null_or_empty(feat[f_uc]):
                    reasons.append("Update Codes is Null")
                else:
                    # 4. If Update Codes is 5: n_hhhead, n_hsn, and m_uc_ind must not be null
                    uc_val = feat[f_uc]
                    if is_update_code_5(uc_val):
                        if f_nhhhead and is_null_or_empty(feat[f_nhhhead]):
                            reasons.append("Update Code 5: n_hhhead is Null")
                        elif not f_nhhhead:
                            reasons.append("Update Code 5: n_hhhead column not found")

                        if f_nhsn and is_null_or_empty(feat[f_nhsn]):
                            reasons.append("Update Code 5: n_hsn is Null")
                        elif not f_nhsn:
                            reasons.append("Update Code 5: n_hsn column not found")

                        if f_mucind and is_null_or_empty(feat[f_mucind]):
                            reasons.append("Update Code 5: m_uc_ind is Null")
                        elif not f_mucind:
                            reasons.append("Update Code 5: m_uc_ind column not found")

                if reasons:
                    layer_errors.append((feat, "; ".join(reasons)))

                processed_count += 1
                if feature_count > 0 and processed_count % max(1, (feature_count // 20)) == 0:
                    prog = 30 + int((processed_count / feature_count) * 60)
                    self.progressBar.setValue(min(prog, 90))
                    QCoreApplication.processEvents()

            err_count = len(layer_errors)
            created_temp_layer = None

            if err_count > 0:
                # Create temporary memory layer for errors
                temp_name = f"Errors_{sample_layer.name()}"
                crs_auth = sample_layer.crs().authid()
                if sample_layer.isSpatial():
                    wkb_type_str = QgsWkbTypes.displayString(sample_layer.wkbType())
                    uri = f"{wkb_type_str}?crs={crs_auth}"
                else:
                    uri = "none"

                temp_layer = QgsVectorLayer(uri, temp_name, "memory")
                t_pr = temp_layer.dataProvider()

                # Copy original fields and add Validation_Errors field
                t_pr.addAttributes(sample_layer.fields())
                try:
                    from qgis.PyQt.QtCore import QMetaType
                    err_field = QgsField("Validation_Errors", QMetaType.Type.QString)
                except Exception:
                    err_field = QgsField("Validation_Errors", QVariant.String)

                t_pr.addAttributes([err_field])
                temp_layer.updateFields()

                new_features = []
                for e_feat, e_reason in layer_errors:
                    nf = QgsFeature(temp_layer.fields())
                    if sample_layer.isSpatial() and e_feat.hasGeometry():
                        nf.setGeometry(e_feat.geometry())
                    attrs = e_feat.attributes()
                    attrs.append(e_reason)
                    nf.setAttributes(attrs)
                    new_features.append(nf)

                t_pr.addFeatures(new_features)
                temp_layer.updateExtents()

                # Apply prominent red symbology
                apply_error_symbology(temp_layer)

                # Add to QGIS Project
                QgsProject.instance().addMapLayer(temp_layer)
                created_temp_layer = temp_layer

            self.progressBar.setValue(100)
            QCoreApplication.processEvents()

            # Set active layer and zoom canvas if errors exist
            if created_temp_layer and hasattr(self, "iface") and self.iface:
                self.iface.setActiveLayer(created_temp_layer)
                if (
                    created_temp_layer.isSpatial()
                    and created_temp_layer.featureCount() > 0
                    and self.iface.mapCanvas()
                ):
                    self.iface.mapCanvas().setExtent(created_temp_layer.extent())
                    self.iface.mapCanvas().refresh()

            if err_count == 0:
                QMessageBox.information(
                    self,
                    "No Errors Found",
                    f"Checker completed successfully!\n\nAll {feature_count} records in '{sample_layer.name()}' passed validation.",
                )
            else:
                QMessageBox.warning(
                    self,
                    "Validation Errors Found",
                    f"Found {err_count} error feature(s) out of {feature_count} in '{sample_layer.name()}'.\n\n"
                    f"A new temporary layer '{created_temp_layer.name()}' has been created in QGIS with the error records.",
                )

        except Exception as e:
            QMessageBox.critical(
                self, "Unexpected Error", f"An error occurred during checking:\n{e}"
            )
        finally:
            self.runButton.setEnabled(True)

    def reset_fields(self):
        """Resets the input fields and progress bar."""
        self.progressBar.setValue(0)
        self.populate_layers()

    def closeEvent(self, event):
        """Clean close event."""
        self.progressBar.setValue(0)
        event.accept()
