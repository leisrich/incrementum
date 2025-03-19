#!/usr/bin/env python
"""
Test script for YouTube timestamp tracking in Incrementum.
This script simulates saving and loading a timestamp for a YouTube video.
"""

import os
import sys
import json
import tempfile
import logging
from datetime import datetime

# Add the parent directory to Python path to ensure proper imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup logging
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Mock the database session and document
class MockSession:
    def __init__(self):
        self.committed = False
        self.position_value = None
    
    def commit(self):
        self.committed = True
        logger.info(f"Committed position: {self.position_value}")
    
    def query(self, cls):
        return self
    
    def get(self, doc_id):
        from collections import namedtuple
        Doc = namedtuple('Document', ['id', 'title', 'file_path', 'position', 'source_url'])
        
        # Create a test document with the video ID
        video_id = "dQw4w9WgXcQ"  # Rick Roll video
        
        # Create a temporary metadata file
        temp_dir = tempfile.gettempdir()
        metadata_file = os.path.join(temp_dir, f"{video_id}.json")
        
        with open(metadata_file, 'w') as f:
            json.dump({
                'video_id': video_id,
                'title': 'Test Video',
                'author': 'Test Author',
                'source_url': f'https://www.youtube.com/watch?v={video_id}'
            }, f)
        
        logger.info(f"Created test metadata file at {metadata_file}")
        
        doc = Doc(
            id=1, 
            title='Test Video',
            file_path=metadata_file,
            position=30,  # Start at 30 seconds
            source_url=f'https://www.youtube.com/watch?v={video_id}'
        )
        return doc

# PyQt Application
try:
    from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton, QLabel, QHBoxLayout
    from PyQt6.QtCore import Qt, QTimer
    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtWebChannel import QWebChannel
        HAS_WEBENGINE = True
    except ImportError:
        HAS_WEBENGINE = False
        logger.error("QtWebEngine not available, cannot run YouTube test")
        sys.exit(1)
except ImportError:
    logger.error("PyQt6 not available, cannot run YouTube test")
    sys.exit(1)

class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YouTube Timestamp Test")
        self.resize(800, 600)
        
        # Create central widget
        central = QWidget()
        self.setCentralWidget(central)
        
        # Create layout
        layout = QVBoxLayout(central)
        
        # Label to show status
        self.status_label = QLabel("Loading video...")
        layout.addWidget(self.status_label)
        
        # Log output display
        self.log_display = QLabel("Logs will appear here...")
        self.log_display.setStyleSheet("background-color: #eee; color: #333; padding: 5px; border: 1px solid #ccc;")
        self.log_display.setWordWrap(True)
        self.log_display.setMinimumHeight(100)
        layout.addWidget(self.log_display)
        
        # Create session and get document
        self.db_session = MockSession()
        self.document = self.db_session.query(None).get(1)
        
        # Create web view
        self.webview = QWebEngineView()
        layout.addWidget(self.webview)
        
        # Add buttons
        button_layout = QVBoxLayout()
        
        # Position control buttons
        position_layout = QHBoxLayout()
        
        test_button = QPushButton("Test Position Save (30s)")
        test_button.clicked.connect(self.test_position_save)
        position_layout.addWidget(test_button)
        
        test_button2 = QPushButton("Test Position Save (60s)")
        test_button2.clicked.connect(lambda: self.test_position_save(60))
        position_layout.addWidget(test_button2)
        
        test_button3 = QPushButton("Test Position Save (90s)")
        test_button3.clicked.connect(lambda: self.test_position_save(90))
        position_layout.addWidget(test_button3)
        
        button_layout.addLayout(position_layout)
        
        # Control buttons
        control_layout = QHBoxLayout()
        
        restart_button = QPushButton("Restart Video")
        restart_button.clicked.connect(self.restart_video)
        control_layout.addWidget(restart_button)
        
        debug_button = QPushButton("Run Debug Tests")
        debug_button.clicked.connect(self.run_debug_tests)
        control_layout.addWidget(debug_button)
        
        button_layout.addLayout(control_layout)
        
        layout.addLayout(button_layout)
        
        # Setup the video
        self.setup_video()
        
        # Timer to simulate playback
        self.timer = QTimer(self)
        self.timer.setInterval(1000)  # 1 second
        self.timer.timeout.connect(self.update_status)
        self.timer.start()
        
        # Current time counter
        self.current_time = 0
        self.document.position = 0  # Reset position for test
        
        # Set up custom logger
        self.setup_logger()
    
    def setup_logger(self):
        """Set up a custom logger handler to display logs in the UI"""
        class UILogHandler(logging.Handler):
            def __init__(self, callback):
                super().__init__()
                self.callback = callback
                self.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
            
            def emit(self, record):
                msg = self.format(record)
                self.callback(msg)
        
        # Add our custom handler
        handler = UILogHandler(self.log_message)
        handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(handler)
        
        # Log startup message
        logger.info("YouTube timestamp test started")
    
    def log_message(self, message):
        """Display log message in the UI"""
        # Keep only the last 10 lines
        current_text = self.log_display.text()
        lines = current_text.split('\n')
        if len(lines) > 10:
            lines = lines[1:10]
        lines.append(message)
        self.log_display.setText('\n'.join(lines))
    
    def setup_video(self):
        """Set up the YouTube video using the helper module"""
        try:
            from ui.load_youtube_helper import setup_youtube_webview
            
            logger.info("Setting up YouTube video test")
            success, self.callback = setup_youtube_webview(
                document=self.document,
                webview=self.webview,
                db_session=self.db_session,
                restore_position=True
            )
            
            if success:
                logger.info("Video loaded successfully")
                self.status_label.setText("Video loaded successfully")
                self.current_time = self.document.position or 0
            else:
                logger.error("Failed to load video")
                self.status_label.setText("Failed to load video")
        except Exception as e:
            logger.exception(f"Error setting up video: {e}")
            self.status_label.setText(f"Error: {str(e)}")
    
    def update_status(self):
        """Update the status label with current playback information"""
        self.current_time += 1
        
        # Get position from callback if available
        if hasattr(self, 'callback') and self.callback and hasattr(self.callback, 'current_position'):
            position = self.callback.current_position
        else:
            position = self.current_time
        
        self.status_label.setText(
            f"Playback position: {position:.1f}s | "
            f"Stored position: {getattr(self.document, 'position', 0) or 0}s | "
            f"DB committed: {getattr(self.db_session, 'committed', False)}"
        )
        
        # Simulate updating the callback's position
        if hasattr(self, 'callback') and self.callback:
            self.callback.current_position = self.current_time
    
    def test_position_save(self, position=None):
        """Test saving the position"""
        if position is not None:
            self.current_time = position
            if hasattr(self, 'callback') and self.callback:
                self.callback.current_position = position
        
        if hasattr(self, 'callback') and self.callback:
            try:
                self.callback._save_position()
                logger.info(f"Position saved: {self.callback.current_position:.1f}s")
                self.status_label.setText(f"Position saved: {self.callback.current_position:.1f}s")
            except Exception as e:
                logger.exception(f"Error saving position: {e}")
                self.status_label.setText(f"Error saving position: {str(e)}")
        else:
            logger.warning("Callback not available")
            self.status_label.setText("Callback not available")
    
    def restart_video(self):
        """Restart the video with stored position"""
        # Re-get the document with updated position
        self.document = self.db_session.query(None).get(1)
        logger.info(f"Restarting video at position: {self.document.position or 0}s")
        self.setup_video()
        self.status_label.setText(f"Video restarted at position: {self.document.position or 0}s")
    
    def run_debug_tests(self):
        """Run various debug tests to diagnose WebChannel issues"""
        logger.info("Running debug tests")
        
        # Test 1: Check if callback exists
        has_callback = hasattr(self, 'callback') and self.callback is not None
        logger.info(f"Callback exists: {has_callback}")
        
        # Test 2: Check WebChannel status
        if has_callback and hasattr(self.webview, 'page'):
            has_channel = hasattr(self.webview.page(), 'webChannel') and self.webview.page().webChannel() is not None
            logger.info(f"WebChannel exists: {has_channel}")
        
        # Test 3: Run JavaScript debug code
        debug_js = """
        (function() {
            var results = {
                hasQt: typeof qt !== 'undefined',
                hasQtWebChannel: typeof QWebChannel !== 'undefined',
                hasTransport: typeof qt !== 'undefined' && qt.webChannelTransport !== undefined,
                hasBackend: typeof window.backend !== 'undefined',
                statusElement: document.getElementById('status') ? document.getElementById('status').textContent : 'No status element'
            };
            
            return JSON.stringify(results);
        })();
        """
        
        def log_js_result(result):
            try:
                data = json.loads(result)
                logger.info(f"JS Debug: {result}")
                
                # Add debug message to page
                if data.get('hasQt', False) and data.get('hasQtWebChannel', False):
                    update_js = """
                    document.getElementById('status').textContent = 'Debug: WebChannel available';
                    """
                    self.webview.page().runJavaScript(update_js)
            except Exception as e:
                logger.error(f"Error parsing JS debug result: {e}")
        
        try:
            self.webview.page().runJavaScript(debug_js, log_js_result)
        except Exception as e:
            logger.exception(f"Error running JS debug: {e}")
    
    def closeEvent(self, event):
        """Handle close event"""
        if hasattr(self, 'callback') and self.callback:
            try:
                self.callback._save_position()
                logger.info("Final position saved on close")
            except Exception as e:
                logger.exception(f"Error saving position on close: {e}")
        super().closeEvent(event)

def main():
    """Main entry point"""
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 