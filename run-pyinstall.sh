#!/bin/bash
# Complete PyInstaller Build Script for Incrementum
# Handles Qt, SciPy, and scikit-learn dependencies

# Colors for console output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Convenience functions
echo_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
echo_warn() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
echo_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check if in virtual environment
if [ -z "$VIRTUAL_ENV" ]; then
    echo_error "Please activate your virtual environment first"
    echo "Example: source incrementum/bin/activate"
    exit 1
fi

echo_info "Starting complete build process for Incrementum"

# 1. Ensure we have the right dependencies installed
echo_info "Installing required dependencies..."
pip install --upgrade pip setuptools wheel
pip install PyQt6==6.4.0 PyQt6-WebEngine==6.4.0 PyQt6-QtMultimedia==6.4.0 || {
    echo_warn "Could not install specific PyQt6 versions. Using latest versions..."
    pip install PyQt6 PyQt6-WebEngine PyQt6-QtMultimedia
}

# Install scientific packages
echo_info "Installing scientific packages..."
pip install scipy scikit-learn nltk

# Install PyInstaller
echo_info "Installing PyInstaller..."
pip install pyinstaller

# 2. Create a custom hook file for SciPy to ensure all required modules are included
echo_info "Creating custom hooks..."
mkdir -p hooks

# SciPy hook
cat > hooks/hook-scipy.py << 'EOF'
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# Collect all submodules
hiddenimports = collect_submodules('scipy')

# Specifically add the missing module
hiddenimports.extend([
    'scipy._lib.array_api_compat.numpy.fft',
    'scipy._lib.array_api_compat.numpy.linalg',
    'scipy.sparse.csgraph._validation',
    'scipy.sparse.linalg.eigen.arpack',
    'scipy.sparse.linalg.isolve.iterative',
    'scipy.sparse.linalg._expm_multiply',
    'scipy.special._ellip_harm_2',
    'scipy.special._ufuncs',
])

# Get data files
datas = collect_data_files('scipy')
EOF

# scikit-learn hook
cat > hooks/hook-sklearn.py << 'EOF'
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# Collect all submodules
hiddenimports = collect_submodules('sklearn')
hiddenimports.extend([
    'sklearn.utils._cython_blas',
    'sklearn.neighbors.quad_tree',
    'sklearn.neighbors.typedefs',
    'sklearn.tree._utils',
    'sklearn.utils._typedefs',
])

# Get data files
datas = collect_data_files('sklearn')
EOF

# NLTK hook
cat > hooks/hook-nltk.py << 'EOF'
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# Collect all submodules
hiddenimports = collect_submodules('nltk')

# Get data files
datas = collect_data_files('nltk')
EOF

# PyQt6 runtime hook
cat > hooks/pyi_rth_qt6_fixed.py << 'EOF'
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
EOF

# 3. Create our comprehensive spec file
echo_info "Creating comprehensive spec file..."
cat > complete.spec << 'EOF'
# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# Collect all necessary data files and dependencies
scipy_imports = collect_submodules('scipy')
sklearn_imports = collect_submodules('sklearn')
nltk_imports = collect_submodules('nltk')
spacy_imports = collect_submodules('spacy')

# Combine all hidden imports
all_hidden_imports = [
    'PyQt6',
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'PyQt6.QtWebEngine',
    'PyQt6.QtWebEngineCore',
    'PyQt6.QtWebEngineWidgets',
    'PyQt6.QtMultimedia',
    'PyQt6.QtPrintSupport',
    'sqlalchemy',
    'sqlalchemy.sql.default_comparator',
    'pdfminer',
    'PyPDF2',
    'beautifulsoup4',
    'bs4',
    'ebooklib',
    'markdown',
    'docx',
    'pymupdf',
    'pydantic',
    'numpy.core._dtype_ctypes',
    'pandas',
    'matplotlib',
    'matplotlib.backends.backend_qt5agg',
    'pkg_resources.py2_warn',
]

# Add all collected submodules to hidden imports
all_hidden_imports.extend(scipy_imports)
all_hidden_imports.extend(sklearn_imports)
all_hidden_imports.extend(nltk_imports)
all_hidden_imports.extend(spacy_imports)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets', 'assets'),
        ('ui/styles', 'ui/styles'),
        ('data', 'data'),
    ],
    hiddenimports=all_hidden_imports,
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=['hooks/pyi_rth_qt6_fixed.py'],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Create a list of all binary libraries
# to ensure proper bundling of Qt and other dependencies
binaries_to_include = []

# Ensure Qt libraries are properly bundled
qt_base_path = None
for p in a.pure:
    if p[0].startswith('PyQt6/Qt6'):
        qt_base_path = os.path.dirname(p[0])
        break

if qt_base_path:
    # Find all Qt libraries in the Qt path
    for root, dirs, files in os.walk(os.path.join(qt_base_path, 'lib')):
        for file in files:
            if file.endswith('.so') or file.endswith('.dll'):
                source = os.path.join(root, file)
                target = os.path.join('PyQt6/Qt6/lib', file)
                binaries_to_include.append((source, target))

# Add binaries to the Analysis
a.binaries.extend(binaries_to_include)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Incrementum',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Incrementum',
)
EOF

# 4. Run PyInstaller with the complete spec
echo_info "Running PyInstaller with comprehensive spec..."
python -m PyInstaller --clean complete.spec

# 5. Fix library permissions in the built application
if [ -d "dist/Incrementum" ]; then
    echo_info "Fixing library permissions..."
    find dist/Incrementum -name "*.so*" -exec chmod +x {} \;
fi

# 6. Check if build was successful
if [ -d "dist/Incrementum" ]; then
    echo_info "==========================================="
    echo_info "Build successful! The executable is in dist/Incrementum/"
    echo_info "To run the application: dist/Incrementum/Incrementum"
    echo_info "==========================================="
else
    echo_error "Build failed. Please check the output for errors."
    exit 1
fi
