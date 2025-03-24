#!/usr/bin/env python3
"""
Debug wrapper for Incrementum application
This script wraps the main application with additional logging to identify where it gets stuck
"""

import os
import sys
import time
import logging
import traceback

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.FileHandler("incrementum_debug.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("DebugWrapper")
logger.info("Starting debug wrapper for Incrementum")

# Create a custom excepthook to catch any unhandled exceptions
def custom_excepthook(exc_type, exc_value, exc_traceback):
    logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))
    sys.__excepthook__(exc_type, exc_value, exc_traceback)

sys.excepthook = custom_excepthook

# Set environment variables to enable PyQt debugging
os.environ['QT_DEBUG_PLUGINS'] = '1'
os.environ['PYQT_DEBUG'] = '1'

# Import and monkey-patch key modules to add logging
logger.info("Setting up module import logging")

# Store the original import machinery
original_import = __builtins__.__import__

# Track imported modules
imported_modules = set()

def verbose_import(name, *args, **kwargs):
    """Log module imports to help identify where the code might be hanging"""
    if name not in imported_modules:
        logger.debug(f"Importing module: {name}")
        imported_modules.add(name)
    
    try:
        module = original_import(name, *args, **kwargs)
        return module
    except Exception as e:
        logger.error(f"Error importing {name}: {e}")
        raise

# Replace the built-in import with our verbose version
__builtins__.__import__ = verbose_import

# Create a watchdog timer to periodically check if the application is responsive
def start_watchdog():
    """Start a watchdog thread to monitor the application"""
    import threading
    
    def watchdog():
        last_checkpoint = time.time()
        checkpoint_count = 0
        
        while True:
            time.sleep(5)  # Check every 5 seconds
            current_time = time.time()
            
            # Print active threads to help diagnose where we might be stuck
            if current_time - last_checkpoint > 10:  # If more than 10 seconds since last checkpoint
                logger.warning(f"Application may be stuck. No checkpoints for {current_time - last_checkpoint:.1f} seconds")
                
                # Log all active threads
                logger.warning("Active threads:")
                for thread in threading.enumerate():
                    logger.warning(f"  Thread: {thread.name}, daemon: {thread.daemon}")
                
                # Log the current call stack of all threads
                for thread_id, frame in sys._current_frames().items():
                    logger.warning(f"Thread {thread_id} call stack:")
                    logger.warning(''.join(traceback.format_stack(frame)))
            
            # Update checkpoint every 30 seconds regardless
            checkpoint_count += 1
            if checkpoint_count % 6 == 0:
                logger.info(f"Watchdog checkpoint {checkpoint_count//6}")
                last_checkpoint = current_time
    
    watchdog_thread = threading.Thread(target=watchdog, daemon=True, name="Watchdog")
    watchdog_thread.start()
    logger.info("Watchdog thread started")
    return watchdog_thread

logger.info("Starting application...")

try:
    # Import the actual application modules
    import main
    
    # Start the watchdog
    watchdog_thread = start_watchdog()
    
    # Run the application's main function if it exists
    if hasattr(main, 'main'):
        logger.info("Calling main.main()")
        main.main()
    else:
        # Otherwise, assume the main module runs automatically on import
        logger.info("main module has no main() function, continuing with normal execution")
    
    logger.info("Application has exited, terminating debug wrapper")

except Exception as e:
    logger.critical(f"Fatal error in application: {e}", exc_info=True)
    sys.exit(1)# Debug wrapper code goes here - replace with the content from the debug-wrapper artifact
