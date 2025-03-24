# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['debug_wrapper.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets', 'assets'),
        ('ui/styles', 'ui/styles'),
        ('data', 'data'),
    ],
    hiddenimports=[
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.QtWebEngine',
        'PyQt6.QtWebEngineCore',
        'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtMultimedia', 
        'sqlalchemy',
        'nltk',
        'spacy',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=True,  # Important for debugging - don't compress code
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Incrementum-Debug',
    debug=True,  # Enable debug info
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # Don't use UPX compression
    console=True,  # Show console for logging
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Incrementum-Debug',
)
