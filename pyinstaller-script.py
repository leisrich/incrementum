#!/usr/bin/env python3
"""
PyInstaller Build Script for Incrementum
---------------------------------------
This script builds Incrementum using PyInstaller for Windows, macOS, and Linux.
"""

import os
import sys
import platform
import subprocess
import shutil
from pathlib import Path

# Configuration
APP_NAME = "Incrementum"
VERSION = "1.0.0"
MAIN_FILE = "main.py"
ICON_PATH = os.path.join("assets", "icons", "incrementum.png")
WINDOWS_ICON_PATH = os.path.join("assets", "icons", "incrementum.ico")

def print_colored(message, color="green"):
    """Print colored messages to terminal."""
    colors = {
        "green": "\033[92m",
        "yellow": "\033[93m",
        "red": "\033[91m",
        "blue": "\033[94m",
        "end": "\033[0m"
    }
    print(f"{colors.get(color, colors['green'])}{message}{colors['end']}")

def run_command(command, shell=False):
    """Run a shell command and handle errors."""
    try:
        print_colored(f"Running: {' '.join(command) if isinstance(command, list) else command}", "blue")
        result = subprocess.run(
            command,
            shell=shell,
            check=True,
            text=True,
            capture_output=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print_colored(f"Command failed: {e}", "red")
        print_colored(f"Error output: {e.stderr}", "red")
        return None

def install_dependencies():
    """Install required dependencies."""
    print_colored("Installing PyInstaller and dependencies...", "blue")
    run_command([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    run_command([sys.executable, "-m", "pip", "install", "--upgrade", "setuptools", "wheel"])
    run_command([sys.executable, "-m", "pip", "install", "PyInstaller==6.0.0"])
    
    # Install project dependencies
    if os.path.exists("requirements.txt"):
        print_colored("Installing project dependencies from requirements.txt...", "blue")
        run_command([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    else:
        print_colored("No requirements.txt found, skipping dependency installation.", "yellow")

def create_spec_file():
    """Create a PyInstaller .spec file."""
    print_colored("Creating PyInstaller .spec file...", "blue")
    
    platform_system = platform.system().lower()
    
    # Choose the appropriate icon based on platform
    if platform_system == "windows":
        icon_path = WINDOWS_ICON_PATH if os.path.exists(WINDOWS_ICON_PATH) else ICON_PATH
    else:
        icon_path = ICON_PATH
    
    # Data files to include
    data_files = [
        ("assets", "assets"),
        ("data", "data"),
        ("ui/styles", "ui/styles")
    ]
    
    # Create data pairs string for spec file
    data_pairs = ", ".join([f"('{src}', '{dst}')" for src, dst in data_files])
    
    # Create the spec file content
    spec_content = f"""# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['{MAIN_FILE}'],
    pathex=[],
    binaries=[],
    datas=[{data_pairs}],
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
        'pdfminer',
        'PyPDF2',
        'beautifulsoup4',
        'ebooklib',
        'markdown',
        'docx',
        'pymupdf',
        'pytesseract'
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='{APP_NAME}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['{icon_path}'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='{APP_NAME}',
)

# For macOS, create an app bundle
if '{platform_system}' == 'darwin':
    app = BUNDLE(
        coll,
        name='{APP_NAME}.app',
        icon='{icon_path}',
        bundle_identifier='com.yourdomain.incrementum',
        info_plist={{
            'CFBundleShortVersionString': '{VERSION}',
            'NSHighResolutionCapable': 'True',
        }},
    )
"""
    
    # Write the spec file
    with open(f"{APP_NAME}.spec", "w") as f:
        f.write(spec_content)
        
    print_colored(f"Created {APP_NAME}.spec file", "green")
    return f"{APP_NAME}.spec"

def build_application(spec_file):
    """Build the application using PyInstaller."""
    print_colored(f"Building {APP_NAME} using PyInstaller...", "blue")
    
    # Run PyInstaller with the spec file
    result = run_command([
        sys.executable, 
        "-m", 
        "pyinstaller", 
        "--clean",
        spec_file
    ])
    
    if result:
        print_colored(f"{APP_NAME} successfully built!", "green")
        output_dir = os.path.join("dist", APP_NAME)
        print_colored(f"Output directory: {os.path.abspath(output_dir)}", "green")
    else:
        print_colored("Build failed.", "red")
        return False
    
    return True

def create_installer():
    """Create an installer for the application."""
    platform_system = platform.system().lower()
    
    if platform_system == "windows":
        create_windows_installer()
    elif platform_system == "darwin":
        create_macos_installer()
    elif platform_system == "linux":
        create_linux_installer()
    else:
        print_colored(f"Installer creation not supported for {platform_system}", "yellow")

def create_windows_installer():
    """Create a Windows installer using NSIS."""
    print_colored("Creating Windows installer...", "blue")
    
    # Check if NSIS is installed
    makensis_path = shutil.which("makensis")
    if not makensis_path:
        print_colored("NSIS not found. Please install NSIS to create a Windows installer.", "yellow")
        print_colored("Windows installer creation skipped.", "yellow")
        return
    
    # Create NSIS script
    nsis_script = f"""
; Incrementum Installer Script
!include "MUI2.nsh"

Name "{APP_NAME}"
OutFile "dist\\{APP_NAME}-{VERSION}-Setup.exe"
InstallDir "$PROGRAMFILES\\{APP_NAME}"
InstallDirRegKey HKCU "Software\\{APP_NAME}" ""

;--------------------------------
; Interface Settings
!define MUI_ABORTWARNING

;--------------------------------
; Pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

;--------------------------------
; Languages
!insertmacro MUI_LANGUAGE "English"

;--------------------------------
; Installer Sections
Section "Install"
    SetOutPath "$INSTDIR"
    File /r "dist\\{APP_NAME}\\*.*"
    
    ; Create uninstaller
    WriteUninstaller "$INSTDIR\\Uninstall.exe"
    
    ; Create shortcut
    CreateDirectory "$SMPROGRAMS\\{APP_NAME}"
    CreateShortCut "$SMPROGRAMS\\{APP_NAME}\\{APP_NAME}.lnk" "$INSTDIR\\{APP_NAME}.exe"
    CreateShortCut "$DESKTOP\\{APP_NAME}.lnk" "$INSTDIR\\{APP_NAME}.exe"
    
    ; Write registry keys for uninstall
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" "DisplayName" "{APP_NAME}"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" "UninstallString" '"$INSTDIR\\Uninstall.exe"'
    WriteRegDWORD HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" "NoModify" 1
    WriteRegDWORD HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" "NoRepair" 1
SectionEnd

;--------------------------------
; Uninstaller Section
Section "Uninstall"
    ; Remove files and directories
    Delete "$INSTDIR\\Uninstall.exe"
    RMDir /r "$INSTDIR"
    
    ; Remove shortcuts
    Delete "$SMPROGRAMS\\{APP_NAME}\\{APP_NAME}.lnk"
    RMDir "$SMPROGRAMS\\{APP_NAME}"
    Delete "$DESKTOP\\{APP_NAME}.lnk"
    
    ; Remove registry keys
    DeleteRegKey HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}"
    DeleteRegKey HKCU "Software\\{APP_NAME}"
SectionEnd
"""
    
    # Write NSIS script to file
    with open("installer.nsi", "w") as f:
        f.write(nsis_script)
    
    # Run NSIS compiler
    run_command(["makensis", "installer.nsi"])
    
    print_colored(f"Windows installer created: dist\\{APP_NAME}-{VERSION}-Setup.exe", "green")

def create_macos_installer():
    """Create a macOS DMG installer."""
    print_colored("Creating macOS DMG installer...", "blue")
    
    # Check if create-dmg is installed
    create_dmg_path = shutil.which("create-dmg")
    if not create_dmg_path:
        print_colored("create-dmg not found. Please install create-dmg to create a macOS DMG.", "yellow")
        print_colored("macOS installer creation skipped.", "yellow")
        return
    
    # Run create-dmg
    run_command([
        "create-dmg",
        "--volname", f"{APP_NAME} Installer",
        "--volicon", ICON_PATH,
        "--window-pos", "200", "120",
        "--window-size", "800", "400",
        "--icon-size", "100",
        "--icon", f"{APP_NAME}.app", "200", "190",
        "--hide-extension", f"{APP_NAME}.app",
        "--app-drop-link", "600", "185",
        f"dist/{APP_NAME}-{VERSION}.dmg",
        f"dist/{APP_NAME}.app"
    ])
    
    print_colored(f"macOS DMG installer created: dist/{APP_NAME}-{VERSION}.dmg", "green")

def create_linux_installer():
    """Create Linux distribution packages."""
    print_colored("Creating Linux packages...", "blue")
    
    # Check for package managers
    if shutil.which("dpkg"):
        create_deb_package()
    elif shutil.which("rpmbuild"):
        create_rpm_package()
    else:
        print_colored("No supported package manager found (dpkg or rpmbuild).", "yellow")
        print_colored("Linux package creation skipped.", "yellow")
        
def create_deb_package():
    """Create a Debian package."""
    print_colored("Creating Debian package...", "blue")
    
    # Create directory structure
    deb_dir = Path("dist/deb")
    bin_dir = deb_dir / "usr/local/bin"
    app_dir = deb_dir / f"usr/local/lib/{APP_NAME}"
    desktop_dir = deb_dir / "usr/share/applications"
    icon_dir = deb_dir / "usr/share/icons/hicolor/128x128/apps"
    debian_dir = deb_dir / "DEBIAN"
    
    for d in [bin_dir, app_dir, desktop_dir, icon_dir, debian_dir]:
        d.mkdir(parents=True, exist_ok=True)
    
    # Copy application files
    shutil.copytree(f"dist/{APP_NAME}", app_dir, dirs_exist_ok=True)
    
    # Create launcher script
    with open(bin_dir / APP_NAME.lower(), "w") as f:
        f.write(f"""#!/bin/sh
exec /usr/local/lib/{APP_NAME}/{APP_NAME} "$@"
""")
    os.chmod(bin_dir / APP_NAME.lower(), 0o755)
    
    # Create desktop file
    with open(desktop_dir / f"{APP_NAME.lower()}.desktop", "w") as f:
        f.write(f"""[Desktop Entry]
Name={APP_NAME}
Comment=Knowledge management system with spaced repetition
Exec=/usr/local/bin/{APP_NAME.lower()}
Icon={APP_NAME.lower()}
Terminal=false
Type=Application
Categories=Education;Science;
""")
    
    # Copy icon
    shutil.copy(ICON_PATH, icon_dir / f"{APP_NAME.lower()}.png")
    
    # Create control file
    with open(debian_dir / "control", "w") as f:
        f.write(f"""Package: {APP_NAME.lower()}
Version: {VERSION}
Section: education
Priority: optional
Architecture: amd64
Maintainer: Your Name <your.email@example.com>
Description: Knowledge management system with spaced repetition
 Incrementum is a comprehensive knowledge management system
 that helps users organize and retain information through
 spaced repetition learning techniques.
""")
    
    # Create package
    run_command(f"dpkg-deb --build dist/deb dist/{APP_NAME.lower()}_{VERSION}_amd64.deb", shell=True)
    
    print_colored(f"Debian package created: dist/{APP_NAME.lower()}_{VERSION}_amd64.deb", "green")

def create_rpm_package():
    """Create an RPM package."""
    print_colored("Creating RPM package...", "blue")
    
    # Create RPM spec file
    spec_content = f"""Name: {APP_NAME.lower()}
Version: {VERSION}
Release: 1%{{?dist}}
Summary: Knowledge management system with spaced repetition

License: MIT
URL: https://github.com/yourusername/{APP_NAME.lower()}

%description
{APP_NAME} is a comprehensive knowledge management system
that helps users organize and retain information through
spaced repetition learning techniques.

%install
mkdir -p %{{buildroot}}/usr/local/lib/{APP_NAME}
mkdir -p %{{buildroot}}/usr/local/bin
mkdir -p %{{buildroot}}/usr/share/applications
mkdir -p %{{buildroot}}/usr/share/icons/hicolor/128x128/apps

cp -r dist/{APP_NAME}/* %{{buildroot}}/usr/local/lib/{APP_NAME}/

# Create launcher script
cat > %{{buildroot}}/usr/local/bin/{APP_NAME.lower()} << EOF
#!/bin/sh
exec /usr/local/lib/{APP_NAME}/{APP_NAME} "$@"
EOF
chmod 755 %{{buildroot}}/usr/local/bin/{APP_NAME.lower()}

# Create desktop file
cat > %{{buildroot}}/usr/share/applications/{APP_NAME.lower()}.desktop << EOF
[Desktop Entry]
Name={APP_NAME}
Comment=Knowledge management system with spaced repetition
Exec=/usr/local/bin/{APP_NAME.lower()}
Icon={APP_NAME.lower()}
Terminal=false
Type=Application
Categories=Education;Science;
EOF

# Copy icon
cp {ICON_PATH} %{{buildroot}}/usr/share/icons/hicolor/128x128/apps/{APP_NAME.lower()}.png

%files
/usr/local/lib/{APP_NAME}
/usr/local/bin/{APP_NAME.lower()}
/usr/share/applications/{APP_NAME.lower()}.desktop
/usr/share/icons/hicolor/128x128/apps/{APP_NAME.lower()}.png

%changelog
* Sun Mar 23 2025 Your Name <your.email@example.com> - {VERSION}-1
- Initial package
"""
    
    with open(f"{APP_NAME.lower()}.spec", "w") as f:
        f.write(spec_content)
    
    # Build RPM package
    run_command(f"rpmbuild -bb {APP_NAME.lower()}.spec", shell=True)
    
    print_colored(f"RPM package created in rpmbuild/RPMS/", "green")

def main():
    """Main function to build the application and create installers."""
    print_colored("="*60, "blue")
    print_colored(f"PyInstaller Build Script for {APP_NAME}", "blue")
    print_colored("="*60, "blue")
    
    # Check if PyInstaller is installed
    install_dependencies()
    
    # Create .spec file
    spec_file = create_spec_file()
    
    # Build the application
    if build_application(spec_file):
        # Create installer
        create_installer()
        
        print_colored("\nBuild completed successfully!", "green")
        print_colored(f"The executable is in dist/{APP_NAME}/", "green")
    else:
        print_colored("Build failed. Please check the error messages above.", "red")

if __name__ == "__main__":
    main()
