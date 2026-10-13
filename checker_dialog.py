# Developer: TechCraft by Chano
# email: c.dacpano@psa.gov.ph
# GeoFASU_Mod - Checker Module

import os
import re
from pathlib import Path

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QMessageBox
from qgis.PyQt.QtCore import Qt, QCoreApplication, QVariant
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsField,
    QgsProviderRegistry,
    QgsWkbTypes,
    QgsMarkerSymbol,
    QgsFillSymbol,
    QgsLineSymbol,
    QgsSingleSymbolRenderer,
)
from qgis.gui import QgsFileWidget

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
        self.comboxLayer.setPlaceholderText("-- Select Layer to Check --")

        self.gpkgFileWidget.setStorageMode(QgsFileWidget.GetFile)
        self.gpkgFileWidget.setFilter("GeoPackage (*.gpkg)")

        # Initial instruction in result box
        self.resultText.setText(
            "Instructions:\n"
            "1. Choose a GeoPackage (.gpkg) file.\n"
            "2. Select the layer to check (or check all vector layers).\n"
            "3. Click 'Run Checker' to validate records.\n\n"
            "Active Rules:\n"
            "• BSN, HUSN, and HSN columns must NOT be Null.\n"
            "• If Update Codes = 5: n_hhhead, n_hsn, and m_uc_ind must NOT be Null.\n\n"
            "Any errors found will automatically be loaded as a new temporary layer."
        )

        # Signal connections
        self.gpkgFileWidget.fileChanged.connect(self.populate_layer_list)
        self.runButton.clicked.connect(self.run_checker)
        self.closeButton.clicked.connect(self.close)

    def populate_layer_list(self):
        """Populates the layer dropdown from the selected GeoPackage file."""
        self.comboxLayer.blockSignals(True)
        self.comboxLayer.clear()
        self.progressBar.setValue(0)

        gpkg_path = self.gpkgFileWidget.filePath().strip()
        if not gpkg_path or not os.path.isfile(gpkg_path):
            self.comboxLayer.blockSignals(False)
            return

        try:
            sublayers = (
                QgsProviderRegistry.instance()
                .providerMetadata("ogr")
                .querySublayers(gpkg_path)
            )
            valid_layers = []
            for sub in sublayers:
                sub_name = sub.name()
                if sub_name.lower() not in ["layer_styles", "sqlite_sequence"]:
                    valid_layers.append(sub_name)

            if valid_layers:
                if len(valid_layers) > 1:
                    self.comboxLayer.addItem("[All Vector Layers]")
                for layer_name in valid_layers:
                    self.comboxLayer.addItem(layer_name)
                self.comboxLayer.setCurrentIndex(0)
                self.resultText.setText(
                    f"Loaded GeoPackage: {os.path.basename(gpkg_path)}\n"
                    f"Found {len(valid_layers)} layer(s): {', '.join(valid_layers)}\n"
                    f"Ready to check."
                )
            else:
                self.resultText.setText(
                    f"Warning: No valid vector layers found in {os.path.basename(gpkg_path)}."
                )
        except Exception as e:
            self.resultText.setText(f"Error reading GeoPackage layers: {e}")

        self.comboxLayer.blockSignals(False)

    def run_checker(self):
        """Executes the validation check and creates a temporary layer for errors."""
        gpkg_path = self.gpkgFileWidget.filePath().strip()
        if not gpkg_path or not os.path.isfile(gpkg_path):
            QMessageBox.warning(
                self,
                "Missing File",
                "Please select a valid GeoPackage (.gpkg) file to check.",
            )
            return

        selected_layer_text = self.comboxLayer.currentText().strip()
        if not selected_layer_text:
            QMessageBox.warning(
                self,
                "No Layer Selected",
                "Please select a layer from the dropdown list.",
            )
            return

        self.runButton.setEnabled(False)
        self.progressBar.setValue(5)
        self.resultText.clear()
        QCoreApplication.processEvents()

        try:
            # Determine which layers to inspect
            sublayers = (
                QgsProviderRegistry.instance()
                .providerMetadata("ogr")
                .querySublayers(gpkg_path)
            )
            available_sublayers = [
                sub.name()
                for sub in sublayers
                if sub.name().lower() not in ["layer_styles", "sqlite_sequence"]
            ]

            if selected_layer_text == "[All Vector Layers]":
                target_layers = available_sublayers
            else:
                target_layers = [selected_layer_text]

            if not target_layers:
                QMessageBox.warning(
                    self,
                    "No Layers Found",
                    "No valid vector layers were found in the selected GeoPackage.",
                )
                return

            total_layers = len(target_layers)
            overall_error_count = 0
            created_temp_layers = []
            log_messages = []
            log_messages.append(f"GeoPackage: {os.path.basename(gpkg_path)}")
            log_messages.append(f"Layers to check: {', '.join(target_layers)}")
            log_messages.append("=" * 45)

            for idx, lyr_name in enumerate(target_layers):
                layer_uri = f"{gpkg_path}|layername={lyr_name}"
                layer = QgsVectorLayer(layer_uri, lyr_name, "ogr")
                if not layer.isValid():
                    log_messages.append(f"Could not load layer '{lyr_name}' (Invalid).")
                    continue

                feature_count = layer.featureCount()
                log_messages.append(
                    f"\nChecking layer: '{lyr_name}' ({feature_count} features)"
                )

                # Resolve column names
                f_bsn = find_field_name(layer, "BSN", ["bsn", "BS_No"])
                f_husn = find_field_name(layer, "HUSN", ["husn", "HU_SN"])
                f_hsn = find_field_name(layer, "HSN", ["hsn"])
                f_uc = find_field_name(
                    layer,
                    "Update Codes",
                    ["Update_Codes", "update codes", "update_code", "Update Code", "UC"],
                )
                f_nhhhead = find_field_name(
                    layer, "n_hhhead", ["n_hh_head", "nhhhead", "n_head", "new_hhhead"]
                )
                f_nhsn = find_field_name(layer, "n_hsn", ["nhsn", "new_hsn"])
                f_mucind = find_field_name(layer, "m_uc_ind", ["mucind", "m_uc", "muc_ind"])

                # Check if core columns are present
                missing_core = []
                if not f_bsn:
                    missing_core.append("BSN")
                if not f_husn:
                    missing_core.append("HUSN")
                if not f_hsn:
                    missing_core.append("HSN")

                if missing_core:
                    warn_msg = (
                        f"Layer '{lyr_name}' is missing columns: {', '.join(missing_core)}. "
                        "Skipping standard serial number check for this layer."
                    )
                    log_messages.append(warn_msg)
                    if len(target_layers) == 1:
                        QMessageBox.warning(self, "Missing Columns", warn_msg)
                        return
                    continue

                # Inspect features
                layer_errors = []
                processed_count = 0
                step_start_prog = int((idx / total_layers) * 80)
                step_span = int(80 / total_layers)

                for feat in layer.getFeatures():
                    reasons = []

                    # 1. BSN, HUSN, HSN must not be null
                    if is_null_or_empty(feat[f_bsn]):
                        reasons.append("BSN is Null")
                    if is_null_or_empty(feat[f_husn]):
                        reasons.append("HUSN is Null")
                    if is_null_or_empty(feat[f_hsn]):
                        reasons.append("HSN is Null")

                    # 2. If Update Codes is 5: n_hhhead, n_hsn, and m_uc_ind must not be null
                    if f_uc:
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
                        sub_prog = step_start_prog + int((processed_count / feature_count) * step_span)
                        self.progressBar.setValue(min(sub_prog, 90))
                        QCoreApplication.processEvents()

                # Report for current layer
                err_count = len(layer_errors)
                overall_error_count += err_count

                if err_count == 0:
                    log_messages.append(
                        f"  ✓ Passed: 0 errors detected out of {feature_count} features."
                    )
                else:
                    log_messages.append(
                        f"  ✗ Errors detected: {err_count} of {feature_count} features."
                    )
                    # Create temporary memory layer for errors
                    temp_name = f"Errors_{lyr_name}"
                    crs_auth = layer.crs().authid()
                    if layer.isSpatial():
                        wkb_type_str = QgsWkbTypes.displayString(layer.wkbType())
                        uri = f"{wkb_type_str}?crs={crs_auth}"
                    else:
                        uri = "none"

                    temp_layer = QgsVectorLayer(uri, temp_name, "memory")
                    t_pr = temp_layer.dataProvider()

                    # Copy original fields and add error details
                    t_pr.addAttributes(layer.fields())
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
                        if layer.isSpatial() and e_feat.hasGeometry():
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
                    created_temp_layers.append(temp_layer)
                    log_messages.append(
                        f"  → Created temporary layer: '{temp_name}' ({err_count} features)"
                    )

            self.progressBar.setValue(100)
            QCoreApplication.processEvents()

            # Set active layer and zoom canvas if errors exist
            if created_temp_layers and hasattr(self, "iface") and self.iface:
                last_temp = created_temp_layers[-1]
                self.iface.setActiveLayer(last_temp)
                if (
                    last_temp.isSpatial()
                    and last_temp.featureCount() > 0
                    and self.iface.mapCanvas()
                ):
                    self.iface.mapCanvas().setExtent(last_temp.extent())
                    self.iface.mapCanvas().refresh()

            # Final summary
            log_messages.append("\n" + "=" * 45)
            log_messages.append(
                f"SUMMARY: Total Errors Found = {overall_error_count}"
            )
            if created_temp_layers:
                layer_names_str = ", ".join([l.name() for l in created_temp_layers])
                log_messages.append(
                    f"Temporary Layer(s) Created in QGIS: {layer_names_str}"
                )
            self.resultText.setText("\n".join(log_messages))

            if overall_error_count == 0:
                QMessageBox.information(
                    self,
                    "No Errors Found",
                    "Checker completed successfully!\n\nAll records passed the validation checks.",
                )
            else:
                QMessageBox.warning(
                    self,
                    "Validation Errors Found",
                    f"Found {overall_error_count} error feature(s).\n\n"
                    f"A new temporary layer has been created in QGIS with the error records.",
                )

        except Exception as e:
            QMessageBox.critical(
                self, "Unexpected Error", f"An error occurred during checking:\n{e}"
            )
        finally:
            self.runButton.setEnabled(True)

    def reset_fields(self):
        """Resets the input fields and progress bar."""
        self.gpkgFileWidget.setFilePath("")
        self.comboxLayer.clear()
        self.progressBar.setValue(0)
        self.resultText.clear()

    def closeEvent(self, event):
        """Clean close event."""
        self.progressBar.setValue(0)
        event.accept()
