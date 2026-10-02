# Author: Mapping_Kalinga
# email: c.dacpano@psa.gov.ph
# Refactored for robustness and clarity.

import os
import shutil
import pandas as pd

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QMessageBox
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtGui import QPixmap
from qgis.core import (
    QgsVectorLayer,
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsFields,
    QgsVectorFileWriter,
    QgsField,
    QgsGeometry,
)
from qgis.gui import QgsFileWidget

# Load the UI class from the .ui file
FORM_CLASS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "GeoFASU_dialog_base.ui")
)

class GeoFASUDialog(QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        """Initializes the dialog."""
        super().__init__(parent)
        self.setupUi(self)
        self.progressBar.setValue(0)
        self.runButton.clicked.connect(self.run_process)
        self.outputDirWidget.setStorageMode(QgsFileWidget.GetDirectory)
        self.typeofS.setFocus()

    def run_process(self):
        """Main function to execute the entire process when the 'Run' button is clicked."""
        csv_path = self.csvFileWidget.filePath()
        out_dir = self.outputDirWidget.filePath()
        folder_name = self.typeofS.text().strip()

        # --- 1. Input Validation ---
        if not all([csv_path, out_dir, folder_name]):
            QMessageBox.warning(
                self,
                "Missing Input",
                "Please provide all inputs: Excel file, output directory, and survey name.",
            )
            return

        try:
            # --- 2. Read and Prepare Data ---
            df = self._read_and_combine_sheets(csv_path)

            if df is None or df.empty:
                # Error message is shown inside the reading function
                return

            # --- 3. Create Output Directories ---
            project_folder = os.path.join(out_dir, 'Projects', folder_name)
            qfield_folder = os.path.join(out_dir, 'Package for Qfield', folder_name)
            validation_folder = os.path.join(out_dir, 'Validation Output', folder_name)
            filepinas_folder = os.path.join(out_dir, 'Filepinas', folder_name)
            excel_folder = os.path.join(out_dir, 'Excel', folder_name)
            os.makedirs(project_folder, exist_ok=True)
            os.makedirs(qfield_folder, exist_ok=True)
            os.makedirs(validation_folder, exist_ok=True)
            os.makedirs(filepinas_folder, exist_ok=True)
            os.makedirs(excel_folder, exist_ok=True)

            # --- 4. Process and Export Data ---
            self._export_to_geopackages(df, project_folder, filepinas_folder, excel_folder)

            QMessageBox.information(self, "Success", "GeoPackages created successfully.")

        except Exception as e:
            QMessageBox.critical(self, "An Unexpected Error Occurred", f"Error: {e}")
        finally:
            self.reset_fields()

    def _read_and_combine_sheets(self, csv_path):
        """
        Reads 'Sample SSU' (required) and 'Replacement SSU' (optional) sheets.
        Returns a combined and cleaned DataFrame, or None if the required sheet is missing.
        """
        df_sample = None
        df_replacement = None

        # --- 1. Read the REQUIRED 'Sample SSU' sheet ---
        try:
            df_sample = pd.read_excel(csv_path, sheet_name='Sample SSU', dtype=str)
            print("✅ 'Sample SSU' sheet loaded.")
        except (ValueError, KeyError):
            QMessageBox.critical(
                self,
                "Required Sheet Missing",
                "The required sheet 'Sample SSU' was not found in the Excel file. The process cannot continue.",
            )
            return None # Stop the process because the required sheet is missing

        # --- 2. Read the OPTIONAL 'Replacement SSU' sheet ---
        try:
            df_replacement = pd.read_excel(csv_path, sheet_name='Replacement SSU', dtype=str)
            print("✅ 'Replacement SSU' sheet found and will be combined.")
        except (ValueError, KeyError):
            # This is not an error, just an optional step, so we only print a message
            print("⚠️ 'Replacement SSU' sheet not found. Continuing with 'Sample SSU' data only.")
            # df_replacement will remain None

        # --- 3. Combine the dataframes ---
        # Create a list containing only the dataframes that were successfully loaded.
        # df_sample is guaranteed to be here, df_replacement may or may not be.
        valid_dfs = [df for df in [df_sample, df_replacement] if df is not None]
        
        # Combine the data
        df = pd.concat(valid_dfs, ignore_index=True)

        # --- 4. Data Cleaning and Validation ---
        if 'WKT' not in df.columns:
            QMessageBox.critical(self, "Input Error", "A 'WKT' column is required but was not found.")
            return None
            
        df = df.dropna(subset=['WKT'])  # Ensure no missing WKT values
        if df.empty:
            QMessageBox.warning(self, "No Valid Geometries", "No rows with valid WKT geometry were found after cleaning.")
            return None

        df = df.fillna("")  # Fill other missing data with empty strings
        return df

    def _export_to_geopackages(self, df, project_folder, filepinas_folder, excel_folder):
        """
        Iterates through the DataFrame and exports data into structured GeoPackage files.
        """
        crs = QgsCoordinateReferenceSystem("EPSG:4326")
        
        # Check for required grouping columns
        required_cols = ['Mun_name', 'Replicate_Number']
        if not all(col in df.columns for col in required_cols):
            missing = ", ".join([col for col in required_cols if col not in df.columns])
            raise KeyError(f"Missing required column(s) for grouping: {missing}")

        municipalities = df['Mun_name'].unique()
        total_mun = len(municipalities)
        count = 0

        for mun_name, group_mun in df.groupby('Mun_name'):
            mun_project_path = os.path.join(project_folder, str(mun_name))
            mun_filepinas_path = os.path.join(filepinas_folder, str(mun_name))
            mun_excel_path = os.path.join(excel_folder, str(mun_name))
            os.makedirs(mun_project_path, exist_ok=True)
            os.makedirs(mun_filepinas_path, exist_ok=True)
            os.makedirs(mun_excel_path, exist_ok=True)

            for rep_num, group_rep in group_mun.groupby('Replicate_Number'):
                rep_folder_path = os.path.join(mun_project_path, f"R{str(rep_num)}")
                # Overwrite existing folder for this replicate
                if os.path.exists(rep_folder_path):
                    shutil.rmtree(rep_folder_path)
                os.makedirs(rep_folder_path)

                # Create an in-memory layer
                mem_layer = QgsVectorLayer("Point?crs=EPSG:4326", f"{mun_name}_{rep_num}", "memory")
                provider = mem_layer.dataProvider()

                # Define fields from DataFrame columns (excluding WKT)
                fields = QgsFields()
                attr_cols = [col for col in group_rep.columns if col != "WKT"]
                for col in attr_cols:
                    fields.append(QgsField(col, QVariant.String))
                provider.addAttributes(fields)
                mem_layer.updateFields()

                # Add features to the layer
                features = []
                for _, row in group_rep.iterrows():
                    feat = QgsFeature()
                    feat.setAttributes([row[col] for col in attr_cols])
                    geom = QgsGeometry.fromWkt(row["WKT"])
                    
                    if geom and geom.isGeosValid():
                        feat.setGeometry(geom)
                        features.append(feat)
                
                provider.addFeatures(features)
                mem_layer.updateExtents()

                # Write the memory layer to a GeoPackage file
                out_path = os.path.join(rep_folder_path, "Selected SSU_Ref.gpkg")
                QgsVectorFileWriter.writeAsVectorFormat(mem_layer, out_path, "UTF-8", crs, "GPKG")

            count += 1
            self.progressBar.setValue(int((count / total_mun) * 100))

    def reset_fields(self):
        """Resets all input fields and the progress bar to their default state."""
        self.csvFileWidget.setFilePath("")
        self.outputDirWidget.setFilePath("")
        self.typeofS.clear()
        self.progressBar.setValue(0)

    def closeEvent(self, event):
        """Ensures fields are reset when the dialog is closed."""
        self.reset_fields()
        event.accept()