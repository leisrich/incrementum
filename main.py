# main.py - Application entry point

import sys
import logging
from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow
from core.knowledge_base.database import init_database

def setup_logging():
    """Configure application logging."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("incrementum.log"),
            logging.StreamHandler()
        ]
    )

def main():
    """Main application entry point."""
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting Incrementum application")

    # Initialize database
    init_database()
    
    # Start Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("Incrementum")
    app.setOrganizationName("Incrementum")
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    # Execute application
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
