#!/usr/bin/env python3
# test_sync.py - Test script for cloud sync functionality

import sys
import os
import logging
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PyQt6.QtCore import Qt

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Import necessary modules
from core.knowledge_base.models import init_database
from ui.sync_view import SyncView

class TestWindow(QMainWindow):
    """Test window to demonstrate the sync functionality."""
    
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("Incrementum Cloud Sync Test")
        self.setMinimumSize(800, 600)
        
        # Initialize database
        self.db_session = init_database()
        
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Create layout
        layout = QVBoxLayout(central_widget)
        
        # Create sync view
        self.sync_view = SyncView(self.db_session)
        layout.addWidget(self.sync_view)

def main():
    """Main function to run the test."""
    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("Incrementum Sync Test")
    
    # Create and show window
    window = TestWindow()
    window.show()
    
    # Run application
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 