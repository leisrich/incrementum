#!/bin/bash
# macOS direct build script for Incrementum

echo "Building Incrementum for macOS..."

# Clean any previous build artifacts
rm -rf build dist Incrementum.spec

# Run PyInstaller with all necessary options
pyinstaller \
  --name Incrementum \
  --icon assets/icons/incrementum.png \
  --windowed \
  --onefile \
  --clean \
  --noconfirm \
  --add-data assets:assets \
  --hidden-import core.knowledge_base.database \
  --hidden-import core.knowledge_base.database_migration \
  --exclude-module PyQt5 \
  --exclude-module tkinter \
  --exclude-module PySide2 \
  --exclude-module PySide6 \
  --osx-bundle-identifier com.incrementum.app \
  main.py

if [ $? -eq 0 ]; then
  echo "Build completed successfully!"
  echo "Application bundle created at: dist/Incrementum.app"
  
  # Create data directory for database
  mkdir -p dist/data
  
  echo ""
  echo "To run the application:"
  echo "  Open dist/Incrementum.app"
  echo ""
  echo "If you get a security warning:"
  echo "  Right-click (or Control+click) on Incrementum.app and select Open"
else
  echo "Build failed!"
fi 