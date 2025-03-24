#!/bin/bash
# Debug Build Script for Incrementum
# This script creates a standalone debugging version 

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

echo_info "Creating debug build for Incrementum"

# Create the debug wrapper
echo_info "Saving debug_wrapper.py..."
if [ -f "debug_wrapper.py" ]; then
    echo_warn "debug_wrapper.py already exists, backing up..."
    cp debug_wrapper.py debug_wrapper.py.bak
fi

# Copy the debug wrapper we created
cat > debug_wrapper.py << 'EOF'
# Debug wrapper code goes here - replace with the content from the debug-wrapper artifact
EOF

# Check if main.py exists
if [ ! -f "main.py" ]; then
    echo_error "main.py not found. Make sure you're in the Incrementum project directory."
    exit 1
fi

# Create a simplified spec file just for debugging
echo_info "Creating simplified debug spec file..."
cat > debug.spec << 'EOF'
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
EOF

# Build the debug version
echo_info "Building debug version with PyInstaller..."
pip install pyinstaller
python -m PyInstaller --clean debug.spec

# Check if build was successful
if [ -d "dist/Incrementum-Debug" ]; then
    echo_info "Debug build successful!"
    echo_info "To run the debug version: dist/Incrementum-Debug/Incrementum-Debug"
    echo_info "Check incrementum_debug.log for detailed logging"
else
    echo_error "Debug build failed. Please check the output for errors."
    exit 1
fi
