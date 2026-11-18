# Developer: TechCraft by Chano
# email: c.dacpano@psa.gov.ph

import os
import sys

# Ensure embedded packages (qfieldsync, libqfieldsync) are discoverable
plugin_dir = os.path.dirname(__file__)
if plugin_dir not in sys.path:
    sys.path.insert(0, plugin_dir)

os.environ['OPENPYXL_LXML'] = 'False'

# Remove openpyxl from sys.modules if it was already loaded by another plugin
for k in list(sys.modules.keys()):
    if k.startswith('openpyxl'):
        del sys.modules[k]

def classFactory(iface):
    # Purge cached plugin submodules so Plugin Reloader loads fresh code immediately
    for k in list(sys.modules.keys()):
        if any(k.startswith(p) for p in (
            'GeoFASU',
            'checker_dialog',
            'completeness_checker_dialog',
            'gpkg_to_excel_dialog',
            'loader_dialog',
            'post_loader_dialog',
            'folder_creator_dialog',
            'main_dialog',
            'updater',
            'style'
        )):
            del sys.modules[k]

    from .GeoFASU import GeoFASU
    return GeoFASU(iface)
