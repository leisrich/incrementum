#!/usr/bin/env python3

import sys
import logging
from PyQt6.QtWidgets import QApplication
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from core.database import Base

# Configure logging
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

logger.info("Starting test")

# Initialize QApplication
app = QApplication(sys.argv)
logger.info("QApplication initialized")

# Create a database session for testing
logger.info("Creating database session")
engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(engine)
session = Session(engine)
logger.info("Database session created")

# Try to instantiate the editor
try:
    logger.info("Attempting to import LearningItemEditor")
    from ui.learning_item_editor import LearningItemEditor
    logger.info("Import successful")
    
    logger.info("Attempting to instantiate LearningItemEditor")
    editor = LearningItemEditor(session)
    logger.info("LearningItemEditor instantiated successfully!")
except Exception as e:
    logger.error(f"Error: {e}")
    import traceback
    logger.error(traceback.format_exc())

# No need to show the editor or run the app
logger.info("Test completed") 