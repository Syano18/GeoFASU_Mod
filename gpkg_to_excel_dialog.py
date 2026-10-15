# Developer: TechCraft by Chano
# email: c.dacpano@psa.gov.ph

import os
import re
import pandas as pd
from collections import defaultdict

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QMessageBox
from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import QgsVectorLayer, QgsProviderRegistry
import processing

try:
    from .style import apply_modern_style, setup_dialog_logo
except (ImportError, ValueError):
    from style import apply_modern_style, setup_dialog_logo

FORM_CLASS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "gpkg_to_excel_dialog.ui")
)

class GpkgToExcelDialog(QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        apply_modern_style(self)
        setup_dialog_logo(self)
        self.progressBar.setValue(0)
        self.mergeBtn.clicked.connect(self.run_merge)
        self.exportBtn.clicked.connect(self.run_export_excel)
        
        self.comboxNOS.setPlaceholderText("-- Select Type of Survey --")
        self.comboxMun.setPlaceholderText("-- Select City/Municipality --")

        # Signals for dropdowns
        self.fileWidget.fileChanged.connect(self.populate_nos_list)
        self.comboxNOS.currentIndexChanged.connect(self.update_mun_list)

        # Default Reference Directory
        default_ref = r"C:\PSA-GIS\GeoFASU\Kalinga\Project files"
        self.fileWidget.setFilePath(default_ref)
        if os.path.isdir(default_ref):
            self.populate_nos_list()

    def populate_nos_list(self):
        self.comboxNOS.blockSignals(True)
        self.comboxMun.blockSignals(True)

        self.comboxNOS.clear()
        self.comboxMun.clear()
        self.progressBar.setValue(0)

        nos_set = set()
        val_path = os.path.join(self.fileWidget.filePath(), 'Validation Output')
        if os.path.isdir(val_path):
            nos_set.update([d for d in os.listdir(val_path) if os.path.isdir(os.path.join(val_path, d))])
        filepinas_path = os.path.join(self.fileWidget.filePath(), 'Filepinas')
        if os.path.isdir(filepinas_path):
            nos_set.update([d for d in os.listdir(filepinas_path) if os.path.isdir(os.path.join(filepinas_path, d))])

        if nos_set:
            self.comboxNOS.addItems(sorted(list(nos_set)))
            self.comboxNOS.setCurrentIndex(-1)

        self.comboxNOS.blockSignals(False)
        self.comboxMun.blockSignals(False)

    def update_mun_list(self):
        self.comboxMun.blockSignals(True)
        self.comboxMun.clear()
        nos = self.comboxNOS.currentText().strip()
        if nos:
            mun_set = set()
            val_path = os.path.join(self.fileWidget.filePath(), 'Validation Output', nos)
            if os.path.isdir(val_path):
                mun_set.update([d for d in os.listdir(val_path) if os.path.isdir(os.path.join(val_path, d))])
            filepinas_path = os.path.join(self.fileWidget.filePath(), 'Filepinas', nos)
            if os.path.isdir(filepinas_path):
                mun_set.update([d for d in os.listdir(filepinas_path) if os.path.isdir(os.path.join(filepinas_path, d))])

            if mun_set:
                self.comboxMun.addItems(sorted(list(mun_set)))
                self.comboxMun.setCurrentIndex(-1)

        self.comboxMun.blockSignals(False)

    def run_merge(self):
        base_dir = self.fileWidget.filePath().strip()
        nos = self.comboxNOS.currentText().strip()
        mun = self.comboxMun.currentText().strip()

        if not all([base_dir, nos, mun]):
            QMessageBox.warning(
                self,
                "Missing Input",
                "Please ensure all fields are selected (Directory, Survey, and Municipality).",
            )
            self.progressBar.setValue(0)
            return

        mun_dir = os.path.join(base_dir, 'Validation Output', nos, mun)
        if not os.path.isdir(mun_dir):
            QMessageBox.warning(self, "Directory Not Found", f"The directory does not exist:\n{mun_dir}")
            self.progressBar.setValue(0)
            return
        
        # Group GPKG paths by replicate number
        rep_gpkgs = defaultdict(list)
        
        for root, dirs, files in os.walk(mun_dir):
            for file in files:
                if file.endswith('.gpkg'):
                    gpkg_path = os.path.join(root, file)
                    match = re.search(r'_Selected SSU_(R\d+)', gpkg_path)
                    if match:
                        rep_no = match.group(1)
                        rep_gpkgs[rep_no].append(gpkg_path)
                        
        if not rep_gpkgs:
            QMessageBox.warning(
                self,
                "No GeoPackage Found",
                f"No matching .gpkg files (with Replicate Number in filename/path) were found in:\n{mun_dir}"
            )
            self.progressBar.setValue(0)
            return

        filepinas_dir = os.path.join(base_dir, 'Filepinas', nos, mun)
        os.makedirs(filepinas_dir, exist_ok=True)
        
        # Pre-flight check: ensure output files are not locked, and ask for overwrite if any exist
        existing_files = []
        locked_files = []
        
        for rep_no in rep_gpkgs.keys():
            merged_gpkg_name = f"{nos}_{mun}_Selected SSU_{rep_no}.gpkg"
            merged_gpkg_path = os.path.join(filepinas_dir, merged_gpkg_name)
            
            if os.path.exists(merged_gpkg_path):
                existing_files.append(merged_gpkg_path)
                try:
                    with open(merged_gpkg_path, 'a'):
                        pass
                except IOError:
                    locked_files.append(merged_gpkg_path)
                        
        if locked_files:
            locked_msg = "\n".join([os.path.basename(f) for f in locked_files])
            QMessageBox.critical(
                self,
                "Files In Use",
                f"The following GeoPackage files are currently open or locked by another program (like QGIS).\n\nPlease close them and try again:\n\n{locked_msg}"
            )
            self.progressBar.setValue(0)
            return
            
        if existing_files:
            reply = QMessageBox.question(
                self,
                "Overwrite Files?",
                "Some merged GeoPackage files already exist in Filepinas. Do you want to overwrite them?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                self.progressBar.setValue(0)
                return
            for f in existing_files:
                try:
                    os.remove(f)
                except Exception as e:
                    QMessageBox.critical(
                        self,
                        "Error",
                        f"Failed to delete existing file before overwriting:\n{f}\nError: {e}"
                    )
                    self.progressBar.setValue(0)
                    return

        self.mergeBtn.setEnabled(False)
        self.exportBtn.setEnabled(False)
        self.progressBar.setValue(0)
        QCoreApplication.processEvents()

        try:
            total_reps = len(rep_gpkgs)
            current_rep = 0
            
            for rep_no, gpkg_list in rep_gpkgs.items():
                base_prog = int((current_rep / total_reps) * 100)
                self.progressBar.setValue(base_prog + 5)
                QCoreApplication.processEvents()
                
                merged_gpkg_name = f"{nos}_{mun}_Selected SSU_{rep_no}.gpkg"
                merged_gpkg_path = os.path.join(filepinas_dir, merged_gpkg_name)
                
                layers_to_merge = []
                for g in gpkg_list:
                    sublayers = QgsProviderRegistry.instance().providerMetadata('ogr').querySublayers(g)
                    valid_layer = None
                    for sub in sublayers:
                        if sub.name().lower() not in ['layer_styles', 'sqlite_sequence']:
                            l = QgsVectorLayer(sub.uri(), sub.name(), "ogr")
                            if l.isValid() and l.featureCount() > 0:
                                valid_layer = l
                                break
                            elif l.isValid() and valid_layer is None:
                                valid_layer = l
                    if valid_layer:
                        layers_to_merge.append(valid_layer)
                
                if not layers_to_merge:
                    current_rep += 1
                    continue
                    
                # Merge vector layers to memory first
                params = {
                    'LAYERS': layers_to_merge,
                    'CRS': layers_to_merge[0].crs(),
                    'OUTPUT': 'memory:merged_temp'
                }
                temp_merged = processing.run("native:mergevectorlayers", params)['OUTPUT']
                
                self.progressBar.setValue(base_prog + int(50 / total_reps))
                QCoreApplication.processEvents()

                # Delete 'layer', 'path', and 'fid' columns if present to avoid fid UNIQUE constraint violations
                cols_to_del = [c for c in ['layer', 'path', 'fid'] if temp_merged.fields().indexOf(c) != -1]
                if cols_to_del:
                    params_del = {
                        'INPUT': temp_merged,
                        'COLUMN': cols_to_del,
                        'OUTPUT': merged_gpkg_path
                    }
                    processing.run("native:deletecolumn", params_del)
                else:
                    params_save = {
                        'INPUT': temp_merged,
                        'OUTPUT': merged_gpkg_path
                    }
                    processing.run("native:savefeatures", params_save)
                
                current_rep += 1
                self.progressBar.setValue(int((current_rep / total_reps) * 100))
                QCoreApplication.processEvents()
                
            self.progressBar.setValue(100)
            QCoreApplication.processEvents()
            QMessageBox.information(
                self,
                "Success",
                f"Data successfully merged and exported to Filepinas folder:\n{filepinas_dir}"
            )
            self.progressBar.setValue(0)

        except Exception as e:
            QMessageBox.critical(self, "An Unexpected Error Occurred", f"Error: {e}")
            self.progressBar.setValue(0)
        finally:
            self.mergeBtn.setEnabled(True)
            self.exportBtn.setEnabled(True)
            self.progressBar.setValue(0)

    def run_export_excel(self):
        base_dir = self.fileWidget.filePath().strip()
        nos = self.comboxNOS.currentText().strip()
        mun = self.comboxMun.currentText().strip()

        if not all([base_dir, nos, mun]):
            QMessageBox.warning(
                self,
                "Missing Input",
                "Please ensure all fields are selected (Directory, Survey, and Municipality).",
            )
            self.progressBar.setValue(0)
            return

        filepinas_dir = os.path.join(base_dir, 'Filepinas', nos, mun)
        excel_dir = os.path.join(base_dir, 'Excel', nos, mun)

        # Collect merged GPKG files to export
        gpkg_files = []
        if os.path.isdir(filepinas_dir):
            for root, dirs, files in os.walk(filepinas_dir):
                for file in files:
                    if file.endswith('.gpkg'):
                        gpkg_files.append(os.path.join(root, file))

        if not gpkg_files:
            # Check if Validation Output exists to give a clear informative message
            mun_dir = os.path.join(base_dir, 'Validation Output', nos, mun)
            val_has_files = os.path.isdir(mun_dir) and any(
                f.endswith('.gpkg') for _, _, files in os.walk(mun_dir) for f in files
            )
            if val_has_files:
                QMessageBox.warning(
                    self,
                    "Merge Required",
                    f"No merged GeoPackage files found in:\n{filepinas_dir}\n\nPlease click 'Merge' first before exporting to Excel."
                )
            else:
                QMessageBox.warning(
                    self,
                    "No GeoPackage Found",
                    f"No GeoPackage files found in:\n{filepinas_dir}"
                )
            self.progressBar.setValue(0)
            return

        gpkg_files.sort()
        os.makedirs(excel_dir, exist_ok=True)

        # Pre-flight check: ensure excel output files are not locked, and ask for overwrite if any exist
        existing_files = []
        locked_files = []

        for gpkg_path in gpkg_files:
            base_name = os.path.splitext(os.path.basename(gpkg_path))[0]
            excel_path = os.path.join(excel_dir, f"{base_name}.xlsx")

            if os.path.exists(excel_path):
                existing_files.append(excel_path)
                try:
                    with open(excel_path, 'a'):
                        pass
                except IOError:
                    locked_files.append(excel_path)

        if locked_files:
            locked_msg = "\n".join([os.path.basename(f) for f in locked_files])
            QMessageBox.critical(
                self,
                "Files In Use",
                f"The following Excel files are currently open or locked by another program (like Excel).\n\nPlease close them and try again:\n\n{locked_msg}"
            )
            self.progressBar.setValue(0)
            return

        if existing_files:
            reply = QMessageBox.question(
                self,
                "Overwrite Files?",
                "Some Excel output files already exist. Do you want to overwrite them?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                self.progressBar.setValue(0)
                return
            for f in existing_files:
                try:
                    os.remove(f)
                except Exception as e:
                    QMessageBox.critical(
                        self,
                        "Error",
                        f"Failed to delete existing file before overwriting:\n{f}\nError: {e}"
                    )
                    self.progressBar.setValue(0)
                    return

        self.mergeBtn.setEnabled(False)
        self.exportBtn.setEnabled(False)
        self.progressBar.setValue(0)
        QCoreApplication.processEvents()

        try:
            total_files = len(gpkg_files)
            current_file = 0

            for gpkg_path in gpkg_files:
                base_prog = int((current_file / total_files) * 100)
                self.progressBar.setValue(base_prog + 10)
                QCoreApplication.processEvents()

                base_name = os.path.splitext(os.path.basename(gpkg_path))[0]
                excel_name = f"{base_name}.xlsx"
                excel_path = os.path.join(excel_dir, excel_name)

                merged_layer = None
                sublayers = QgsProviderRegistry.instance().providerMetadata('ogr').querySublayers(gpkg_path)
                for sub in sublayers:
                    if sub.name().lower() not in ['layer_styles', 'sqlite_sequence']:
                        merged_layer = QgsVectorLayer(sub.uri(), sub.name(), "ogr")
                        break

                if merged_layer and merged_layer.isValid():
                    field_names = [field.name() for field in merged_layer.fields()]
                    data = []
                    features = merged_layer.getFeatures()

                    for feat in features:
                        row = {}
                        for name in field_names:
                            val = feat[name]
                            if val is None or (hasattr(val, 'isNull') and val.isNull()) or type(val).__name__ == 'QPyNullVariant' or str(val) == 'NULL':
                                val = ""
                            elif 'ID' in name.upper():
                                val = str(val)
                            row[name] = val

                        geom = feat.geometry()
                        if geom and not geom.isNull():
                            row['WKT'] = geom.asWkt()
                        else:
                            row['WKT'] = ""
                        data.append(row)

                    df = pd.DataFrame(data)
                    df = df.fillna("")
                    df.to_excel(excel_path, index=False)

                current_file += 1
                self.progressBar.setValue(int((current_file / total_files) * 100))
                QCoreApplication.processEvents()

            self.progressBar.setValue(100)
            QCoreApplication.processEvents()
            QMessageBox.information(
                self,
                "Success",
                f"Data successfully exported to Excel folder:\n{excel_dir}"
            )
            self.progressBar.setValue(0)

        except Exception as e:
            QMessageBox.critical(self, "An Unexpected Error Occurred", f"Error: {e}")
            self.progressBar.setValue(0)
        finally:
            self.mergeBtn.setEnabled(True)
            self.exportBtn.setEnabled(True)
            self.progressBar.setValue(0)

    def reset_fields(self):
        """Resets all fields to their default state."""
        default_ref = r"C:\PSA-GIS\GeoFASU\Kalinga\Project files"
        self.fileWidget.setFilePath(default_ref)
        self.comboxNOS.blockSignals(True)
        self.comboxMun.blockSignals(True)
        self.comboxNOS.clear()
        self.comboxMun.clear()
        if os.path.isdir(default_ref):
            self.populate_nos_list()
        self.comboxNOS.setCurrentIndex(-1)
        self.comboxMun.setCurrentIndex(-1)
        self.comboxNOS.blockSignals(False)
        self.comboxMun.blockSignals(False)
        self.progressBar.setValue(0)
        self.mergeBtn.setEnabled(True)
        self.exportBtn.setEnabled(True)

    def closeEvent(self, event):
        """Clean close event, resets fields to default."""
        self.reset_fields()
        event.accept()

    def reject(self):
        """Clean reject event, resets fields to default."""
        self.reset_fields()
        super().reject()
