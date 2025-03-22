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

def create_spec_file():
    """Create a PyInstaller spec file with proper configuration."""
    print("Creating PyInstaller spec file...")
    
    # Base command to create the spec file
    pyinstaller_cmd = [
        "pyinstaller",
        "--name", APP_NAME,
        "--icon", ICON_PATH,
        "--windowed",   # No console window
        "--noconfirm",  # Overwrite output directory
        "--log-level", "DEBUG",
        # Include additional modules that might be needed
        "--hidden-import=core.knowledge_base.database",
        "--hidden-import=core.knowledge_base.database_migration",
        "--collect-all", "PyQt6",
        "--exclude-module=PyQt5",
        "--exclude-module=tkinter",
        "--exclude-module=PySide2",
        "--exclude-module=PySide6",
        "--exclude-module=IPython",
        "--exclude-module=matplotlib",
        "--exclude-module=notebook",
        "--exclude-module=jupyter",
        # Only create the spec file for now
        "--onefile",
        MAIN_SCRIPT,
        "--specpath", "."
    ]
    
    # Run PyInstaller to create spec file
    try:
        subprocess.check_call(pyinstaller_cmd)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to create spec file: {e}")
        return False

def modify_spec_file():
    """Modify the spec file to ensure PyQt6 is used and PyQt5 is excluded."""
    spec_file = Path(f"{APP_NAME}.spec")
    if not spec_file.exists():
        print(f"Spec file {spec_file} does not exist. Cannot modify.")
        return False
    
    print(f"Modifying spec file: {spec_file}")
    
    # Read the spec file
    with open(spec_file, 'r') as file:
        content = file.read()
    
    # Add PyQt5 to excludes
    if "excludes=" in content:
        content = content.replace(
            "excludes=[]", 
            "excludes=['PyQt5', 'tkinter', 'PySide2', 'PySide6', 'IPython', 'matplotlib', 'notebook', 'jupyter']"
        )
    else:
        print("Could not find excludes section in spec file.")
        return False
    
    # Ensure datas includes assets
    if "datas=[]" in content:
        assets_path = os.path.join(os.getcwd(), "assets")
        content = content.replace(
            "datas=[]", 
            f"datas=[('assets', 'assets')]"
        )
    
    # Write the modified content back to the spec file
    with open(spec_file, 'w') as file:
        file.write(content)
    
    print("Spec file modified successfully.")
    return True

def build_from_spec():
    """Build the executable using the spec file."""
    spec_file = Path(f"{APP_NAME}.spec")
    if not spec_file.exists():
        print(f"Spec file {spec_file} does not exist. Cannot build.")
        return False
    
    print(f"Building from spec file: {spec_file}")
    
    # Run PyInstaller with the spec file
    try:
        subprocess.check_call(["pyinstaller", "--clean", spec_file])
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to build from spec file: {e}")
        return False

def create_windows_package():
    """Create Windows executable."""
    print("Building Windows package...")
    
    if not create_spec_file():
        return False
    
    if not modify_spec_file():
        return False
    
    if not build_from_spec():
        return False
    
    print(f"Windows package created: dist/{APP_NAME}.exe")
    return True

def create_macos_package():
    """Create macOS .app bundle."""
    print("Building macOS package...")
    
    if not create_spec_file():
        return False
    
    if not modify_spec_file():
        return False
    
    if not build_from_spec():
        return False
    
    print(f"macOS package created: dist/{APP_NAME}.app")
    return True

def create_linux_package():
    """Create Linux executable."""
    print("Building Linux package...")
    
    if not create_spec_file():
        return False
    
    if not modify_spec_file():
        return False
    
    if not build_from_spec():
        return False
    
    print(f"Linux package created: dist/{APP_NAME}")
    
    # Create desktop entry file
    create_linux_desktop_file()
    return True

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
    success = False
    system = args.platform
    
    if system == "all":
        if platform.system().lower() == "windows":
            success = create_windows_package()
        elif platform.system().lower() == "darwin":
            success = create_macos_package()
        elif platform.system().lower() == "linux":
            success = create_linux_package()
        else:
            print(f"Cannot build packages for all platforms from {platform.system()}")
    elif system == "windows":
        success = create_windows_package()
    elif system == "macos" or system == "darwin":
        success = create_macos_package()
    elif system == "linux":
        success = create_linux_package()
    else:
        print(f"Unknown platform: {system}")
        return
    
    if success:
        # Copy any additional dependencies
        copy_dependencies()
        
        # Create platform-specific README
        create_platform_specific_readme()
        
        print(f"\n{APP_NAME} packaging completed successfully!")
    else:
        print(f"\nFailed to create {APP_NAME} package for {system}.")

if __name__ == "__main__":
    main() 