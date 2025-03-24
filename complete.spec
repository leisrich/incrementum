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
