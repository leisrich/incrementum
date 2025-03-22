#!/bin/bash
# Linux direct build script for Incrementum

echo "Building Incrementum for Linux..."

# Determine if we have a virtual environment and activate it
if [ -d "incrementum-env" ]; then
  echo "Activating incrementum-env virtual environment"
  source incrementum-env/bin/activate
elif [ -d "venv_py311" ]; then
  echo "Activating venv_py311 virtual environment"
  source venv_py311/bin/activate
elif [ -d "venv" ]; then
  echo "Activating venv virtual environment"
  source venv/bin/activate
fi

# Check if PyInstaller is installed
if ! command -v pyinstaller &> /dev/null; then
  echo "PyInstaller not found. Installing..."
  pip install pyinstaller
fi

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
  main.py

if [ $? -eq 0 ]; then
  echo "Build completed successfully!"
  echo "Executable created at: dist/Incrementum"
  
  # Create data directory for database
  mkdir -p dist/data
  
  # Create desktop entry file
  cat > dist/incrementum.desktop << EOF
[Desktop Entry]
Name=Incrementum
Comment=Incremental Learning System
Exec=$(pwd)/dist/Incrementum
Icon=$(pwd)/assets/icons/incrementum.png
Terminal=false
Type=Application
Categories=Education;Office;
EOF
  
  echo "Desktop entry created at: dist/incrementum.desktop"
  echo ""
  echo "To install desktop entry system-wide:"
  echo "  sudo cp dist/incrementum.desktop /usr/share/applications/"
  echo "  sudo cp assets/icons/incrementum.png /usr/share/icons/hicolor/256x256/apps/"
  echo ""
  echo "To run the application:"
  echo "  chmod +x dist/Incrementum"
  echo "  ./dist/Incrementum"
else
  echo "Build failed!"
fi 