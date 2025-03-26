# Packaging Incrementum

This guide explains how to create single-click installers for Incrementum on Windows, macOS, and Linux platforms.

## Prerequisites

- Python 3.6 or higher
- pip (Python package manager)
- Git (for source code access)

Platform-specific tools:
- **Windows**: Microsoft Visual C++ 14.0 or higher
- **macOS**: Xcode command-line tools
- **Linux**: Development tools (build-essential or equivalent)

## Quick Start

The easiest way to package Incrementum is to use the included `package.py` script:

```bash
# Package for your current platform
python package.py

# Package with clean build
python package.py --clean

# Package for a specific platform
python package.py --platform windows
python package.py --platform macos
python package.py --platform linux
```

## Installation Requirements

The script will automatically install required packaging tools:
- PyInstaller
- setuptools
- wheel

## Output Files

After running the package script, you'll find the packaged applications in the `dist` directory:

- **Windows**: `dist/Incrementum.exe`
- **macOS**: `dist/Incrementum.app`
- **Linux**: `dist/Incrementum` (executable) and `dist/incrementum.desktop` (desktop entry)

## Manual Installation

If you prefer to install the tools manually:

```bash
pip install pyinstaller setuptools wheel
```

## Troubleshooting

### Common Issues

1. **Missing dependencies**: PyInstaller might not detect all dependencies automatically. If the packaged application fails to run, you may need to modify the packaging script to include additional data files or modules.

2. **Windows DLL issues**: On Windows, you might need to add extra DLLs if the application crashes with missing DLL errors.

3. **macOS code signing**: For distribution outside of development, you'll need to sign the macOS app with your developer certificate.

### Platform-Specific Notes

#### Windows
- The Windows package creates a self-contained `.exe` file
- For commercial distribution, consider using NSIS or Inno Setup to create a proper installer

#### macOS
- For distribution on macOS, you should sign the app with your Developer ID
- To create a DMG file for distribution, you can use tools like `create-dmg`

#### Linux
- The Linux package creates a standalone executable and desktop entry file
- For wider distribution, consider creating distribution-specific packages (.deb, .rpm) or use AppImage

## Advanced Usage

### Adding Resources

If your application requires additional files or resources, modify the `copy_dependencies()` function in `package.py`.

### Customizing the Build

The PyInstaller commands can be customized in each platform-specific function:
- `create_windows_package()`
- `create_macos_package()`
- `create_linux_package()` 