#!/usr/bin/env python3

try:
    import sys
    print(f"Python version: {sys.version}")
    print(f"Python executable: {sys.executable}")

    print("Attempting to import PyQt6...")
    import PyQt6
    print(f"PyQt6 version: {PyQt6.__version__}")
    
    print("Importing QtWidgets...")
    from PyQt6 import QtWidgets
    print("QtWidgets imported successfully")

    print("Creating QApplication...")
    app = QtWidgets.QApplication([])
    print("QApplication created successfully")
    
    print("All PyQt6 imports successful!")
except Exception as e:
    print(f"Error: {e}") 