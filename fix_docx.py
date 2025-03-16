#!/usr/bin/env python3
# fix_docx.py - Script to fix the docx dependency issue

import subprocess
import sys
import os

def fix_docx_dependency():
    print("Fixing docx dependency...")
    
    # First, try to uninstall the old, incompatible docx package
    try:
        subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "docx"], 
                      check=False, capture_output=True)
        print("Removed old docx package")
    except Exception as e:
        print(f"Note: Could not uninstall old docx package: {e}")
    
    # Install the correct python-docx package
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "python-docx"], 
                      check=True, capture_output=True)
        print("Successfully installed python-docx")
        return True
    except subprocess.SubprocessError as e:
        print(f"Failed to install python-docx: {e}")
        return False

if __name__ == "__main__":
    if fix_docx_dependency():
        print("DOCX dependency fixed successfully.")
        print("You can now run 'python main.py' to start the application.")
    else:
        print("Failed to fix DOCX dependency.")
        print("Please try manually running: pip uninstall docx && pip install python-docx")
