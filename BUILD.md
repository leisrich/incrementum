# Building Incrementum

This document explains how to build standalone executables for Incrementum on Windows, macOS, and Linux.

## Prerequisites

1. Python 3.6+ with pip
2. Virtual environment (recommended)
3. PyQt6 (the application uses PyQt6)

## Platform-Specific Build Scripts

We provide simple platform-specific build scripts that handle everything for you:

### Windows

1. Open a command prompt
2. Navigate to the Incrementum directory
3. Run: `build_windows.bat`
4. Find the executable at: `dist/Incrementum.exe`

### macOS

1. Open a terminal
2. Navigate to the Incrementum directory
3. Run: `chmod +x build_macos.sh` (first time only)
4. Run: `./build_macos.sh`
5. Find the application at: `dist/Incrementum.app`

### Linux

1. Open a terminal
2. Navigate to the Incrementum directory
3. Run: `chmod +x build_linux.sh` (first time only)
4. Run: `./build_linux.sh`
5. Find the executable at: `dist/Incrementum`

## Manual Build with PyInstaller

If the build scripts don't work for you, you can run PyInstaller manually:

```bash
# Install PyInstaller if you don't have it
pip install pyinstaller

# Basic build command (adjust for your platform)
pyinstaller --name Incrementum \
  --icon assets/icons/incrementum.png \
  --windowed \
  --onefile \
  --clean \
  --add-data assets:assets \
  --hidden-import core.knowledge_base.database \
  --hidden-import core.knowledge_base.database_migration \
  --exclude-module PyQt5 \
  main.py
```

## Troubleshooting

### PyQt5/PyQt6 Conflict

If you get an error about multiple Qt bindings, make sure your environment only has PyQt6 installed, or use the `--exclude-module=PyQt5` flag.

### Missing Assets

If the application runs but can't find its assets, make sure to use the `--add-data` flag with the correct path separator for your platform:

- Windows: `--add-data "assets;assets"`
- macOS/Linux: `--add-data assets:assets`

### Import Errors

If you get import errors for modules, add them with `--hidden-import`:

```bash
pyinstaller --hidden-import=missing_module [other-options] main.py
```

## Additional Resources

- [PyInstaller Documentation](https://pyinstaller.org/en/stable/)
- [PyQt6 Documentation](https://www.riverbankcomputing.com/static/Docs/PyQt6/) 