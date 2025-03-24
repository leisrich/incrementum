#!/usr/bin/env python3
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
