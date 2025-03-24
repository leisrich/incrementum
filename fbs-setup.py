#!/usr/bin/env python3
"""
FBS Setup Script for Incrementum
--------------------------------
This script prepares your Incrementum project for building with fbs by:
1. Creating the fbs project structure
2. Modifying import statements if needed
3. Setting up dependencies correctly
"""

import os
import sys
import shutil
import subprocess
import json
from pathlib import Path

# Configuration
APP_NAME = "Incrementum"
APP_VERSION = "1.0.0"
APP_AUTHOR = "Your Name"
APP_DESCRIPTION = "Knowledge management system with spaced repetition"
MAIN_FILE = "main.py"
ICON_PATH = "assets/icons/incrementum.png"
WINDOWS_ICON_PATH = "assets/icons/incrementum.ico"

# Ensure we're in the project root
if not os.path.exists(MAIN_FILE):
    print(f"Error: Cannot find {MAIN_FILE}. Please run this script from the project root.")
    sys.exit(1)

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

def install_fbs():
    """Install fbs and PyQt6."""
    print_colored("Installing fbs and PyQt6...", "blue")
    run_command([sys.executable, "-m", "pip", "install", "fbs", "PyQt6==6.5.0", "PyQt6-WebEngine==6.5.0", "PyQt6-Multimedia==6.5.0"])

def setup_fbs_project():
    """Initialize the fbs project structure."""
    if os.path.exists("src"):
        print_colored("'src' directory already exists. FBS project may already be initialized.", "yellow")
        response = input("Continue and potentially overwrite files? (y/n): ")
        if response.lower() != 'y':
            print_colored("Aborting setup.", "red")
            sys.exit(0)
    
    # Create directories
    os.makedirs("src/main/python", exist_ok=True)
    os.makedirs("src/main/icons", exist_ok=True)
    os.makedirs("src/main/resources", exist_ok=True)
    os.makedirs("src/build/settings", exist_ok=True)
    
    # Create base settings
    base_settings = {
        "app_name": APP_NAME,
        "version": APP_VERSION,
        "author": APP_AUTHOR,
        "description": APP_DESCRIPTION,
        "main_module": "src/main/python/main"
    }
    
    with open("src/build/settings/base.json", "w") as f:
        json.dump(base_settings, f, indent=4)
    
    # Create platform-specific settings
    os.makedirs("src/build/settings/mac", exist_ok=True)
    with open("src/build/settings/mac/base.json", "w") as f:
        json.dump({
            "mac_bundle_identifier": "com.yourdomain.incrementum"
        }, f, indent=4)
    
    os.makedirs("src/build/settings/linux", exist_ok=True)
    with open("src/build/settings/linux/base.json", "w") as f:
        json.dump({
            "categories": "Education;Science;Database"
        }, f, indent=4)
    
    print_colored("FBS project structure set up successfully!", "green")

def copy_source_files():
    """Copy all source files to the fbs structure."""
    print_colored("Copying source files to fbs structure...", "blue")
    
    # Copy core modules
    if os.path.exists("core"):
        shutil.copytree("core", "src/main/python/core", dirs_exist_ok=True)
    
    # Copy UI modules
    if os.path.exists("ui"):
        shutil.copytree("ui", "src/main/python/ui", dirs_exist_ok=True)
    
    # Copy assets and icons
    if os.path.exists("assets"):
        shutil.copytree("assets", "src/main/python/assets", dirs_exist_ok=True)
        
        # Also copy icons to the fbs icons directory
        if os.path.exists("assets/icons"):
            for icon_file in os.listdir("assets/icons"):
                shutil.copy2(f"assets/icons/{icon_file}", "src/main/icons/")
    
    # Copy necessary Python files
    necessary_files = [
        "main.py", "init_db.py", "setup_dir_structure.py", 
        "migrate_db.py", "fix_dependencies.py"
    ]
    
    for file in necessary_files:
        if os.path.exists(file):
            shutil.copy2(file, f"src/main/python/{file}")
    
    # Copy requirements.txt
    if os.path.exists("requirements.txt"):
        shutil.copy2("requirements.txt", "src/requirements.txt")

def create_fbs_main():
    """Create a main.py that works with fbs."""
    print_colored("Creating fbs-compatible main.py...", "blue")
    
    fbs_main = """#!/usr/bin/env python3
import sys
import os
from fbs_runtime.application_context.PyQt6 import ApplicationContext

# Add the application directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the original main functionality
# You may need to adjust these imports based on your actual code structure
from ui.main_window import MainWindow

class AppContext(ApplicationContext):
    def run(self):
        # Initialize database if needed
        try:
            from init_db import initialize_database
            initialize_database()
        except ImportError:
            print("No database initialization module found.")
        except Exception as e:
            print(f"Error initializing database: {e}")
        
        # Create main window
        window = MainWindow()
        window.show()
        
        # Execute application
        return self.app.exec()

if __name__ == '__main__':
    appctxt = AppContext()
    exit_code = appctxt.run()
    sys.exit(exit_code)
"""
    
    # Back up the original main.py
    if os.path.exists("src/main/python/main.py"):
        shutil.copy2("src/main/python/main.py", "src/main/python/main.py.original")
    
    # Write the new fbs-compatible main.py
    with open("src/main/python/main.py", "w") as f:
        f.write(fbs_main)

def create_manifest():
    """Create a manifest of additional files to include."""
    print_colored("Creating additional files manifest...", "blue")
    
    # Create a basic manifest listing any data files
    manifest = """# This file tells fbs which additional files to include
# Format: target path -> source path

# Data directory
data/
"""
    
    with open("src/main/python/freeze_manifest.txt", "w") as f:
        f.write(manifest)

def main():
    """Main function."""
    print_colored("="*60, "blue")
    print_colored(f"FBS Setup Script for {APP_NAME}", "blue")
    print_colored("="*60, "blue")
    
    # Install fbs
    install_fbs()
    
    # Set up fbs project structure
    setup_fbs_project()
    
    # Copy source files
    copy_source_files()
    
    # Create fbs-compatible main.py
    create_fbs_main()
    
    # Create manifest
    create_manifest()
    
    print_colored("\nSetup completed successfully!", "green")
    print_colored("\nNext steps:", "blue")
    print_colored("1. Review the generated files in the 'src' directory")
    print_colored("2. Build your application with: 'fbs freeze'")
    print_colored("3. Create an installer with: 'fbs installer'")
    print_colored("\nFor cross-platform builds:", "blue")
    print_colored("- Windows: 'fbs freeze --platform=windows' (requires Wine on Linux/macOS)")
    print_colored("- macOS: 'fbs freeze --platform=mac' (macOS only)")
    print_colored("- Linux: 'fbs freeze --platform=linux' (Linux only)")

if __name__ == "__main__":
    main()
