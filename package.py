#!/usr/bin/env python3
"""
Cross-platform packaging script for Incrementum.
This script builds standalone executable packages for Windows, macOS, and Linux.
"""

import os
import sys
import shutil
import subprocess
import platform
import argparse
from pathlib import Path

# Define constants
APP_NAME = "Incrementum"
APP_VERSION = "1.0.0"
MAIN_SCRIPT = "main.py"
ICON_PATH = os.path.join("assets", "icons", "incrementum.ico") if platform.system() == "Windows" else \
            os.path.join("assets", "icons", "incrementum.png")

# Required Python packages for packaging
PACKAGING_REQUIREMENTS = [
    "pyinstaller",
    "setuptools",
    "wheel"
]

def install_packaging_tools():
    """Install required packaging tools."""
    print("Installing packaging tools...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + PACKAGING_REQUIREMENTS)
        return True
    except subprocess.CalledProcessError:
        print("Failed to install packaging tools. Please install them manually.")
        return False

def clean_previous_builds():
    """Clean up previous build artifacts."""
    print("Cleaning previous builds...")
    build_dir = Path("build")
    dist_dir = Path("dist")
    
    if build_dir.exists():
        shutil.rmtree(build_dir)
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
        
    # Also clean PyInstaller spec file if exists
    spec_file = Path(f"{APP_NAME}.spec")
    if spec_file.exists():
        spec_file.unlink()

def create_windows_package():
    """Create Windows executable and installer."""
    print("Building Windows package...")
    
    # Basic PyInstaller command for Windows
    pyinstaller_cmd = [
        "pyinstaller",
        "--name", APP_NAME,
        "--icon", ICON_PATH,
        "--windowed",  # No console window
        "--onefile",   # Single executable file
        "--clean",     # Clean PyInstaller cache
        "--noconfirm", # Overwrite output directory
        "--add-data", f"assets{os.pathsep}assets",  # Include assets directory
        # Include additional modules that might be needed
        "--hidden-import=core.knowledge_base.database",
        "--hidden-import=core.knowledge_base.database_migration",
        MAIN_SCRIPT
    ]
    
    # Run PyInstaller
    subprocess.check_call(pyinstaller_cmd)
    
    print(f"Windows package created: dist/{APP_NAME}.exe")

def create_macos_package():
    """Create macOS .app bundle."""
    print("Building macOS package...")
    
    # PyInstaller command for macOS
    pyinstaller_cmd = [
        "pyinstaller",
        "--name", APP_NAME,
        "--icon", ICON_PATH,
        "--windowed",  # macOS .app bundle
        "--onefile",   # Single executable inside the .app
        "--clean",     # Clean PyInstaller cache
        "--noconfirm", # Overwrite output directory
        "--add-data", f"assets{os.pathsep}assets",  # Include assets directory
        "--osx-bundle-identifier", "com.incrementum.app",  # Bundle identifier
        # Include additional modules that might be needed
        "--hidden-import=core.knowledge_base.database",
        "--hidden-import=core.knowledge_base.database_migration",
        MAIN_SCRIPT
    ]
    
    # Run PyInstaller
    subprocess.check_call(pyinstaller_cmd)
    
    print(f"macOS package created: dist/{APP_NAME}.app")

def create_linux_package():
    """Create Linux executable and AppImage."""
    print("Building Linux package...")
    
    # Basic PyInstaller command for Linux
    pyinstaller_cmd = [
        "pyinstaller",
        "--name", APP_NAME,
        "--icon", ICON_PATH,
        "--windowed",  # No terminal window
        "--onefile",   # Single executable file
        "--clean",     # Clean PyInstaller cache
        "--noconfirm", # Overwrite output directory
        "--add-data", f"assets{os.pathsep}assets",  # Include assets directory
        # Include additional modules that might be needed
        "--hidden-import=core.knowledge_base.database",
        "--hidden-import=core.knowledge_base.database_migration",
        MAIN_SCRIPT
    ]
    
    # Run PyInstaller
    subprocess.check_call(pyinstaller_cmd)
    
    print(f"Linux package created: dist/{APP_NAME}")
    
    # Create desktop entry file
    create_linux_desktop_file()

def create_linux_desktop_file():
    """Create a .desktop file for Linux."""
    desktop_dir = Path("dist")
    desktop_file = desktop_dir / f"{APP_NAME.lower()}.desktop"
    
    desktop_content = f"""[Desktop Entry]
Name={APP_NAME}
Comment=Incremental Learning System
Exec=dist/{APP_NAME}
Icon={os.path.abspath(ICON_PATH)}
Terminal=false
Type=Application
Categories=Education;Office;
"""
    
    with open(desktop_file, "w") as f:
        f.write(desktop_content)
    
    print(f"Linux desktop entry created: {desktop_file}")

def copy_dependencies():
    """Copy non-Python dependencies to the distribution directory."""
    dist_dir = Path("dist")
    
    # Ensure assets folder is copied
    assets_dir = Path("assets")
    if assets_dir.exists():
        dest_assets = dist_dir / "assets"
        if not dest_assets.exists():
            shutil.copytree(assets_dir, dest_assets)
    
    # Create an empty database directory to ensure the app can create its database
    db_dir = dist_dir / "data"
    db_dir.mkdir(exist_ok=True)
    
    # Create empty log file path
    log_file = dist_dir / "incrementum.log"
    if not log_file.exists():
        log_file.touch()
    
    print("Copied all required dependencies and created necessary directories")

def create_platform_specific_readme():
    """Create a platform-specific README file in the dist directory."""
    dist_dir = Path("dist")
    readme_file = dist_dir / "README.txt"
    
    system = platform.system().lower()
    
    if system == "windows":
        content = f"""Incrementum {APP_VERSION}
===================

Thank you for installing Incrementum!

To start the application, simply double-click on Incrementum.exe.

The first time you run the application, it will create a database file.
Any notes, flashcards, and learning materials will be stored in this database.

For support or to report issues:
https://github.com/yourusername/incrementum
"""
    elif system == "darwin":
        content = f"""Incrementum {APP_VERSION}
===================

Thank you for installing Incrementum!

To start the application:
1. Double-click the Incrementum.app bundle
2. If you get a security warning, right-click (or Control+click) on the app and select Open

The first time you run the application, it will create a database file.
Any notes, flashcards, and learning materials will be stored in this database.

For support or to report issues:
https://github.com/yourusername/incrementum
"""
    else:  # Linux
        content = f"""Incrementum {APP_VERSION}
===================

Thank you for installing Incrementum!

To start the application:
1. Make the file executable (if needed): chmod +x Incrementum
2. Run the application: ./Incrementum

The first time you run the application, it will create a database file.
Any notes, flashcards, and learning materials will be stored in this database.

For support or to report issues:
https://github.com/yourusername/incrementum
"""
    
    with open(readme_file, "w") as f:
        f.write(content)
    
    print(f"Created README file in the distribution directory")

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description=f"Package {APP_NAME} for distribution")
    parser.add_argument("--platform", choices=["windows", "macos", "linux", "all"], 
                        default=platform.system().lower(),
                        help="Target platform for packaging")
    parser.add_argument("--clean", action="store_true", help="Clean previous builds")
    
    return parser.parse_args()

def main():
    """Main function."""
    args = parse_arguments()
    
    # Clean if requested
    if args.clean:
        clean_previous_builds()
    
    # Install packaging tools
    if not install_packaging_tools():
        return
    
    # Create platform-specific packages
    system = args.platform
    if system == "all":
        if platform.system().lower() == "windows":
            create_windows_package()
        elif platform.system().lower() == "darwin":
            create_macos_package()
        elif platform.system().lower() == "linux":
            create_linux_package()
        else:
            print(f"Cannot build packages for all platforms from {platform.system()}")
    elif system == "windows":
        create_windows_package()
    elif system == "macos" or system == "darwin":
        create_macos_package()
    elif system == "linux":
        create_linux_package()
    else:
        print(f"Unknown platform: {system}")
        return
    
    # Copy any additional dependencies
    copy_dependencies()
    
    # Create platform-specific README
    create_platform_specific_readme()
    
    print(f"\n{APP_NAME} packaging completed successfully!")

if __name__ == "__main__":
    main() 