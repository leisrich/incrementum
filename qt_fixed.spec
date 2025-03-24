# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
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
        'sqlalchemy',
        'sqlalchemy.sql.default_comparator',
        'nltk',
        'spacy',
        'pdfminer',
        'PyPDF2',
        'beautifulsoup4',
        'bs4',
        'ebooklib',
        'markdown',
        'docx',
        'pymupdf',
        'pydantic',
    ],
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=['hooks/pyi_rth_qt6.py'],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Ensure Qt libraries are properly bundled
qt_path = None
for p in a.pure:
    if p[0].startswith('PyQt6/Qt6'):
        qt_path = os.path.dirname(p[0])
        break

if qt_path:
    # Add all Qt libraries to the bundle
    qt_libs = []
    for root, dirs, files in os.walk(os.path.join(qt_path, 'lib')):
        for file in files:
            if file.endswith('.so') or file.endswith('.dll'):
                qt_libs.append((os.path.join(root, file), os.path.join('PyQt6/Qt6/lib', file)))
    a.binaries.extend(qt_libs)

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
