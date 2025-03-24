#-----------------------------------------------------------------------------
# PyQt6 runtime hook for PyInstaller
#-----------------------------------------------------------------------------

import os
import sys

# Ensure Qt plugin paths are correctly set
if hasattr(sys, 'frozen'):
    # Get the directory where our app is located
    basedir = sys._MEIPASS
    
    # Tell PyQt where to find its plugins
    os.environ['QT_PLUGIN_PATH'] = os.path.join(basedir, 'PyQt6', 'Qt6', 'plugins')
    os.environ['QML2_IMPORT_PATH'] = os.path.join(basedir, 'PyQt6', 'Qt6', 'qml')
    
    # Ensure libraries can be found
    if sys.platform == 'linux':
        lib_path = os.path.join(basedir, 'PyQt6', 'Qt6', 'lib')
        if os.path.isdir(lib_path):
            if 'LD_LIBRARY_PATH' in os.environ:
                os.environ['LD_LIBRARY_PATH'] = lib_path + os.pathsep + os.environ['LD_LIBRARY_PATH']
            else:
                os.environ['LD_LIBRARY_PATH'] = lib_path
