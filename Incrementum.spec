# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Handle spaCy model
spacy_model_datas = []
try:
    import spacy
    import en_core_web_sm
    model_path = en_core_web_sm.__path__[0]
    model_name = os.path.basename(model_path)
    spacy_model_datas = [(model_path, model_name)]
    print(f"Found spaCy model at: {model_path}")
except ImportError:
    print("WARNING: en_core_web_sm not found. Please install with: python -m spacy download en_core_web_sm")

# Patch importlib_load_source to skip problematic pydantic hook
from PyInstaller.compat import importlib_load_source
_orig_importlib_load_source = importlib_load_source

def patched_importlib_load_source(name, path):
    if 'hook-pydantic.py' in path:
        print(f"Skipping problematic hook: {path}")
        class DummyModule:
            hiddenimports = ['pydantic', 'pydantic.main', 'pydantic.fields', 'pydantic.error_wrappers']
            datas = []
            excludedimports = []
        return DummyModule()
    return _orig_importlib_load_source(name, path)

from PyInstaller import compat
compat.importlib_load_source = patched_importlib_load_source

# Collect additional dependencies
nltk_datas = collect_data_files('nltk')
pydantic_hiddenimports = [
    'pydantic',
    'pydantic.main',
    'pydantic.fields',
    'pydantic.error_wrappers',
    'pydantic.types',
    'pydantic.utils',
]

# SciPy and scikit-learn hidden imports
scipy_hiddenimports = [
    'scipy',
    'scipy._lib',
    'scipy._lib.array_api_compat',
    'scipy._lib.array_api_compat.numpy',
    'scipy._lib.array_api_compat.numpy.fft',  # Explicitly include the missing module
    'scipy.sparse',
    'scipy.sparse._base',
    'scipy.sparse._sputils',
]

sklearn_hiddenimports = [
    'sklearn',
    'sklearn.utils',
    'sklearn.utils._chunking',
    'sklearn.utils._param_validation',
    'sklearn.base',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets', 'assets'),
        ('ui/styles', 'ui/styles'),
        ('data', 'data'),
        *nltk_datas,
        *spacy_model_datas,
    ],
    hiddenimports=[
        # PyQt dependencies
        'PyQt6', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets',
        'PyQt6.QtWebEngine', 'PyQt6.QtWebEngineCore', 'PyQt6.QtWebEngineWidgets',
        
        # Database
        'sqlalchemy', 'sqlalchemy.sql.default_comparator',
        
        # NLP dependencies
        'nltk', 'spacy', 'en_core_web_sm', 'spacy.lang.en',
        
        # Document processing
        'pdfminer', 'PyPDF2', 'beautifulsoup4', 'bs4',
        'ebooklib', 'markdown', 'docx', 'pymupdf',
        
        # Pydantic imports
        *pydantic_hiddenimports,
        
        # SciPy and scikit-learn imports
        *scipy_hiddenimports,
        *sklearn_hiddenimports,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['_pyinstaller_hooks_contrib'],
    noarchive=False,
)

pyz = PYZ(a.pure)

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
    console=True,  # Keep True for debugging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/icons/incrementum.png'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Incrementum',
)
