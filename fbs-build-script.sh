#!/bin/bash
# Incrementum - Cross-Platform Build Script using fbs
# This script sets up and builds the Incrementum application for Linux, Windows, and macOS

set -e  # Exit on error

# Configuration
APP_NAME="Incrementum"
APP_VERSION="1.0.0"
APP_AUTHOR="Your Name"
APP_DESCRIPTION="Knowledge management system with spaced repetition"
MAIN_FILE="main.py"
ICON_PATH="assets/icons/incrementum.png"
WINDOWS_ICON_PATH="assets/icons/incrementum.ico"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to print colored messages
print_message() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    print_message "Checking prerequisites..."
    
    if ! command_exists python3; then
        print_error "Python 3 is not installed. Please install it and try again."
        exit 1
    fi
    
    if ! command_exists pip; then
        print_error "pip is not installed. Please install it and try again."
        exit 1
    fi
    
    # Check if we're in a virtual environment
    if [[ -z "$VIRTUAL_ENV" ]]; then
        print_warning "You are not in a virtual environment. It's recommended to use one."
        read -p "Continue anyway? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

# Install fbs and PyQt
install_dependencies() {
    print_message "Installing fbs and PyQt6..."
    pip install fbs PyQt6==6.5.0 PyQt6-WebEngine==6.5.0 PyQt6-QtMultimedia==6.5.0
    
    # Check if fbs was installed correctly
    if ! command_exists fbs; then
        print_error "Failed to install fbs. Please check your Python environment."
        exit 1
    fi
}

# Initialize fbs project
init_fbs_project() {
    print_message "Initializing fbs project structure..."
    
    # Check if src/main/python directory already exists
    if [ -d "src/main/python" ]; then
        print_warning "fbs project structure seems to already exist."
        read -p "Reinitialize? This may overwrite existing files. (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            return
        fi
    fi
    
    # Initialize fbs project (this will ask for app name, etc.)
    fbs startproject
    
    # Set app info in fbs settings
    echo "app_name = '$APP_NAME'" > src/build/settings/base.json
    echo "version = '$APP_VERSION'" >> src/build/settings/base.json
    echo "author = '$APP_AUTHOR'" >> src/build/settings/base.json
    echo "description = '$APP_DESCRIPTION'" >> src/build/settings/base.json
    
    # Create platform-specific settings files
    mkdir -p src/build/settings/mac
    echo '{
        "mac_bundle_identifier": "com.yourdomain.incrementum"
    }' > src/build/settings/mac/base.json
    
    mkdir -p src/build/settings/linux
    echo '{
        "categories": "Education;Science;Database"
    }' > src/build/settings/linux/base.json
}

# Copy source files to fbs structure
copy_source_files() {
    print_message "Copying source files to fbs structure..."
    
    # Create required directories
    mkdir -p src/main/python
    mkdir -p src/main/icons
    mkdir -p src/main/resources
    
    # Copy main script
    cp $MAIN_FILE src/main/python/main.py
    
    # Copy core modules
    cp -r core src/main/python/
    
    # Copy UI modules
    cp -r ui src/main/python/
    
    # Copy assets
    cp -r assets/icons/* src/main/icons/
    
    # Copy database initialization scripts if they exist
    if [ -f "init_db.py" ]; then
        cp init_db.py src/main/python/
    fi
    
    # Create a requirements.txt for fbs
    cp requirements.txt src/requirements.txt
    
    # Create a run script for the built application
    echo '#!/bin/bash
# Run Incrementum
cd "$(dirname "$0")"
./Incrementum' > src/main/resources/run.sh
    chmod +x src/main/resources/run.sh
    
    # Create a run script for Windows
    echo '@echo off
:: Run Incrementum
start Incrementum.exe' > src/main/resources/run.bat
}

# Create main.py wrapper for fbs
create_fbs_main() {
    print_message "Creating fbs main wrapper..."
    
    # Create a new fbs-compatible main.py
    cat > src/main/python/main.py << EOF
import sys
import os
from fbs_runtime.application_context.PyQt6 import ApplicationContext

# Add the application directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the original main function
from core import knowledge_base
from ui.main_window import MainWindow

class AppContext(ApplicationContext):
    def run(self):
        # Create the main window
        window = MainWindow()
        window.show()
        
        # Execute the application
        return self.app.exec()

if __name__ == '__main__':
    appctxt = AppContext()
    exit_code = appctxt.run()
    sys.exit(exit_code)
EOF
}

# Build for the current platform
build_current_platform() {
    print_message "Building for current platform..."
    
    # Freeze the application
    fbs freeze
    
    # Create installer
    fbs installer
    
    print_message "Build completed successfully for current platform!"
    print_message "The executable is in target/Incrementum/"
    print_message "The installer is in target/Incrementum Setup.*"
}

# Function to build for Windows (from Linux/macOS using Wine)
build_windows() {
    if [[ "$(uname)" != "Linux" && "$(uname)" != "Darwin" ]]; then
        print_error "This function should be run from Linux or macOS with Wine installed."
        return 1
    fi
    
    print_message "Building for Windows using Wine..."
    
    # Check if Wine is installed
    if ! command_exists wine; then
        print_error "Wine is not installed. Please install it to build for Windows."
        return 1
    fi
    
    # Check if PyInstaller for Windows is available
    if ! wine pip.exe list | grep -q PyInstaller; then
        print_error "PyInstaller is not installed in Wine. Please install it using 'wine pip.exe install PyInstaller'."
        return 1
    fi
    
    # Try to build
    fbs freeze --platform=windows
    
    # Create installer
    fbs installer --platform=windows
    
    print_message "Windows build completed successfully!"
    print_message "The executable is in target/Incrementum/"
    print_message "The installer is in target/Incrementum Setup.exe"
}

# Function to build for macOS (from macOS only)
build_macos() {
    if [[ "$(uname)" != "Darwin" ]]; then
        print_error "macOS builds can only be created on macOS."
        return 1
    fi
    
    print_message "Building for macOS..."
    
    # Freeze the application
    fbs freeze --platform=mac
    
    # Create DMG
    fbs installer --platform=mac
    
    print_message "macOS build completed successfully!"
    print_message "The application bundle is in target/Incrementum.app/"
    print_message "The DMG is in target/Incrementum.dmg"
}

# Main function
main() {
    print_message "Starting Incrementum build process with fbs..."
    
    check_prerequisites
    install_dependencies
    init_fbs_project
    copy_source_files
    create_fbs_main
    
    # Build for the current platform by default
    build_current_platform
    
    print_message "Build process completed!"
    print_message "To build for specific platforms:"
    print_message "  - For Windows (from Linux/macOS): Run this script with --windows"
    print_message "  - For macOS (from macOS only): Run this script with --macos"
    print_message "  - For Linux (from Linux only): Run this script with --linux"
}

# Parse command line arguments
if [[ $# -gt 0 ]]; then
    case "$1" in
        --windows)
            build_windows
            ;;
        --macos)
            build_macos
            ;;
        --linux)
            build_current_platform
            ;;
        *)
            print_error "Unknown option: $1"
            print_message "Available options: --windows, --macos, --linux"
            exit 1
            ;;
    esac
else
    # No arguments, run the main function
    main
fi
