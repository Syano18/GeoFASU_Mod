import os
os.environ['OPENPYXL_LXML'] = 'False'

# Remove openpyxl from sys.modules if it was already loaded by another plugin
import sys
for k in list(sys.modules.keys()):
    if k.startswith('openpyxl'):
        del sys.modules[k]

def classFactory(iface):
    from .GeoFASU import GeoFASU
    return GeoFASU(iface)
