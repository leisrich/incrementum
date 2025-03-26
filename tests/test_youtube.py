#!/usr/bin/env python
"""
Standalone test script for YouTube timestamp tracking.
"""

import os
import sys
import json
import tempfile
import logging
from datetime import datetime
from collections import namedtuple

# Setup logging
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import PyQt
try:
    from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QPushButton, QLabel
    from PyQt6.QtCore import Qt, QTimer, QUrl, QObject, pyqtSlot
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

# Simple document and session mocks
Doc = namedtuple('Document', ['id', 'title', 'file_path', 'position', 'source_url'])

class MockSession:
    def __init__(self):
        self.committed = False
        self.position_value = None
    
    def commit(self):
        self.committed = True
        logger.info(f"Committed position: {self.position_value}")

# YouTube callback handler
class YouTubeCallback(QObject):
    """Class to handle callbacks from JavaScript in the YouTube player."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.document = None
        self.db_session = None
        self.current_position = 0
        self.video_duration = 0
        self.last_save_position = 0
        self.auto_save_timer = QTimer(self)
        self.auto_save_timer.setInterval(5000)  # Save every 5 seconds
        self.auto_save_timer.timeout.connect(self._auto_save_position)
    
    def setup(self, document, db_session):
        """Set up the callback with document and database session."""
        self.document = document
        self.db_session = db_session
        self.auto_save_timer.start()
        
        # Initialize with last known position
        if hasattr(document, 'position') and document.position:
            self.current_position = document.position
            self.last_save_position = document.position
            logger.debug(f"Initialized YouTube position from document: {self.current_position}s")
    
    @pyqtSlot(int)
    def onPlayerStateChange(self, state):
        """Handle player state changes."""
        # YouTube API states: -1 (unstarted), 0 (ended), 1 (playing), 2 (paused), 3 (buffering), 5 (video cued)
        state_names = {
            -1: "unstarted",
            0: "ended",
            1: "playing",
            2: "paused",
            3: "buffering",
            5: "cued"
        }
        logger.debug(f"YouTube player state changed to {state} ({state_names.get(state, 'unknown')})")
        
        # Save position when video is paused or ended
        if state == 2 or state == 0:
            self._save_position()
    
    @pyqtSlot(float)
    def onTimeUpdate(self, current_time):
        """Handle time updates from the player."""
        # Only update if the value makes sense
        if current_time >= 0:
            self.current_position = current_time
    
    @pyqtSlot(float)
    def onDurationChange(self, duration):
        """Handle duration updates from the player."""
        if duration > 0:
            self.video_duration = duration
    
    def _auto_save_position(self):
        """Automatically save position periodically."""
        # Only save if position has changed significantly
        if self.document and self.current_position > 0:
            # Only save if position changed by more than 3 seconds
            if abs(self.current_position - self.last_save_position) > 3:
                self._save_position()
    
    def _save_position(self):
        """Save the current position to the database."""
        if not self.document or not self.db_session:
            return
        
        # Don't save if position is at the very beginning (0) or the same as last saved
        if self.current_position <= 0 or self.current_position == self.last_save_position:
            return
        
        try:
            # Store position in seconds
            self.document = self.document._replace(position=int(self.current_position))
            self.db_session.position_value = int(self.current_position)
            self.db_session.commit()
            self.last_save_position = self.current_position
            logger.debug(f"Saved YouTube position: {self.current_position:.1f}s for {self.document.title}")
        except Exception as e:
            logger.exception(f"Error saving YouTube position: {e}")

def setup_youtube_webview(document, webview, db_session, restore_position=True):
    """
    Set up YouTube player in a WebView with position tracking.
    """
    if not HAS_WEBENGINE or not isinstance(webview, QWebEngineView):
        return False, None
    
    # Get video ID
    video_id = "dQw4w9WgXcQ"  # Default to Rick Roll
    
    # Get stored position
    target_position = 0
    if restore_position and hasattr(document, 'position') and document.position:
        target_position = document.position
    
    logger.info(f"Setting up YouTube player for video ID: {video_id} at position {target_position}")
    
    # Create callback object for communication with JavaScript
    callback = YouTubeCallback(webview)
    callback.setup(document, db_session)
    
    # IMPORTANT: The WebChannel must be set up BEFORE loading the HTML
    try:
        # Create web channel to communicate with JavaScript
        channel = QWebChannel(webview.page())
        channel.registerObject("backend", callback)
        webview.page().setWebChannel(channel)
        
        # Configure web view settings for better performance
        settings = webview.settings()
        settings.setAttribute(settings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(settings.WebAttribute.PluginsEnabled, True)
        settings.setAttribute(settings.WebAttribute.AutoLoadImages, True)
        settings.setAttribute(settings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(settings.WebAttribute.AllowRunningInsecureContent, True)
        
        # Add debug message after channel setup
        webview.loadFinished.connect(lambda ok: 
            logger.debug(f"YouTube player page load finished, success: {ok}")
        )
        
        # Create HTML for the YouTube player with improved reliability
        youtube_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>{document.title}</title>
            <style>
                body {{
                    margin: 0;
                    padding: 0;
                    overflow: hidden;
                    background-color: #000;
                    color: #fff;
                    font-family: Arial, sans-serif;
                    height: 100vh;
                }}
                .container {{
                    display: flex;
                    flex-direction: column;
                    height: 100vh;
                }}
                .header {{
                    padding: 10px;
                    background-color: #202020;
                    border-bottom: 1px solid #303030;
                }}
                .header h1 {{
                    margin: 0;
                    padding: 0;
                    font-size: 18px;
                }}
                .header p {{
                    margin: 5px 0 0 0;
                    font-size: 14px;
                    color: #aaa;
                }}
                .video-container {{
                    flex: 1;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    background: #000;
                }}
                iframe {{
                    width: 100%;
                    height: 100%;
                    border: none;
                }}
                #status {{
                    position: fixed;
                    bottom: 0;
                    left: 0;
                    right: 0;
                    background: rgba(0,0,0,0.7);
                    color: white;
                    padding: 5px 10px;
                    font-size: 12px;
                }}
                #controls {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 10px;
                    background-color: #202020;
                    border-top: 1px solid #303030;
                }}
                button {{
                    background: #3ea6ff;
                    color: black;
                    border: none;
                    padding: 8px 15px;
                    border-radius: 3px;
                    cursor: pointer;
                    font-weight: bold;
                }}
                button:hover {{
                    background: #4db5ff;
                }}
                button:disabled {{
                    background: #555;
                    color: #999;
                    cursor: not-allowed;
                }}
                .time-display {{
                    color: #aaa;
                    font-size: 14px;
                }}
            </style>
            <!-- Load Qt WebChannel library to connect with Python -->
            <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{document.title}</h1>
                    <p>{getattr(document, 'author', 'Unknown author')}</p>
                </div>
                <div class="video-container">
                    <iframe 
                        id="youtube-player"
                        src="https://www.youtube.com/embed/{video_id}?enablejsapi=1&autoplay=1&start={target_position}" 
                        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" 
                        allowfullscreen>
                    </iframe>
                </div>
                <div id="controls">
                    <div class="time-display">
                        Position: <span id="current-time">0:00</span> / <span id="duration">0:00</span>
                    </div>
                    <button id="save-position">Save Position</button>
                </div>
                <div id="status">Loading player...</div>
            </div>
            
            <script>
                // Global variables
                let player = null;
                let playerReady = false;
                let currentTime = {target_position};
                let duration = 0;
                let statusElement = document.getElementById('status');
                let currentTimeDisplay = document.getElementById('current-time');
                let durationDisplay = document.getElementById('duration');
                let saveButton = document.getElementById('save-position');
                let backendObj = null;
                let channelConnected = false;
                let connectionAttempts = 0;
                const maxConnectionAttempts = 10;
                
                // Set initial time display
                currentTimeDisplay.textContent = formatTime(currentTime);
                
                // Disable save button until backend is connected
                saveButton.disabled = true;
                
                // Format time (seconds) to MM:SS
                function formatTime(seconds) {{
                    if (isNaN(seconds) || seconds < 0) return '0:00';
                    
                    const minutes = Math.floor(seconds / 60);
                    const remainingSeconds = Math.floor(seconds % 60);
                    return `${{minutes}}:${{remainingSeconds.toString().padStart(2, '0')}}`;
                }}
                
                // Connect to Qt WebChannel
                function connectToBackend() {{
                    try {{
                        connectionAttempts++;
                        statusElement.textContent = 'Connecting to Qt WebChannel, attempt ' + connectionAttempts;
                        
                        if (typeof QWebChannel === 'undefined') {{
                            statusElement.textContent = 'QWebChannel library not loaded, retrying...';
                            if (connectionAttempts < maxConnectionAttempts) {{
                                setTimeout(connectToBackend, 500);
                            }} else {{
                                statusElement.textContent = 'QWebChannel library missing - position saving disabled';
                            }}
                            return;
                        }}
                        
                        if (typeof qt === 'undefined' || !qt.webChannelTransport) {{
                            statusElement.textContent = 'Qt transport not available, retrying...';
                            if (connectionAttempts < maxConnectionAttempts) {{
                                setTimeout(connectToBackend, 500);
                            }} else {{
                                statusElement.textContent = 'Qt transport missing - position saving disabled';
                            }}
                            return;
                        }}
                        
                        statusElement.textContent = 'Setting up WebChannel...';
                        
                        // Connect to the Qt WebChannel
                        new QWebChannel(qt.webChannelTransport, function(channel) {{
                            if (!channel || !channel.objects) {{
                                statusElement.textContent = 'Channel objects not available';
                                return;
                            }}
                            
                            // Get the backend object
                            backendObj = channel.objects.backend;
                            
                            if (backendObj) {{
                                channelConnected = true;
                                statusElement.textContent = 'Connected to Python backend';
                                saveButton.disabled = false;
                                
                                // Set current position and initialize
                                backendObj.onTimeUpdate(currentTime);
                                
                                // Set duration estimate
                                backendObj.onDurationChange(3600);
                                
                                // Start position tracking now that we're connected
                                if (!window.positionInterval) {{
                                    startPositionTracking();
                                }}
                            }} else {{
                                statusElement.textContent = 'Backend object "backend" not found in channel';
                                console.error('Available objects:', channel.objects);
                                
                                if (connectionAttempts < maxConnectionAttempts) {{
                                    setTimeout(connectToBackend, 500);
                                }}
                            }}
                        }});
                    }} catch (e) {{
                        statusElement.textContent = 'Error connecting to backend: ' + e.message;
                        console.error('Channel connection error:', e);
                        
                        if (connectionAttempts < maxConnectionAttempts) {{
                            setTimeout(connectToBackend, 500);
                        }}
                    }}
                }}
                
                // YouTube API functions
                function onYouTubeIframeAPIReady() {{
                    statusElement.textContent = 'YouTube API ready, initializing player...';
                    
                    try {{
                        let playerFrame = document.getElementById('youtube-player');
                        
                        // If using iframe directly, track loading
                        if (playerFrame.tagName === 'IFRAME') {{
                            playerFrame.onload = function() {{
                                statusElement.textContent = 'YouTube iframe loaded';
                                
                                // Start position tracking as fallback if needed
                                if (!window.positionInterval) {{
                                    startPositionTracking();
                                }}
                            }};
                        }}
                    }} catch (e) {{
                        statusElement.textContent = 'Error initializing player: ' + e.message;
                        console.error('Error initializing player:', e);
                    }}
                }}
                
                // Simple position tracking with JavaScript
                function startPositionTracking() {{
                    // Check if we already have a tracking interval
                    if (window.positionInterval) {{
                        clearInterval(window.positionInterval);
                    }}
                    
                    statusElement.textContent = 'Position tracking active';
                    
                    // Update position every second
                    window.positionInterval = setInterval(function() {{
                        try {{
                            // Increment as fallback
                            currentTime += 1;
                            
                            // Update display
                            currentTimeDisplay.textContent = formatTime(currentTime);
                            durationDisplay.textContent = formatTime(duration || 3600);
                            
                            // Signal to Qt backend if connected
                            if (channelConnected && backendObj) {{
                                backendObj.onTimeUpdate(currentTime);
                                
                                // Update status occasionally (every 30 seconds)
                                if (Math.floor(currentTime) % 30 === 0) {{
                                    statusElement.textContent = `Position: ${{formatTime(currentTime)}} (auto-save enabled)`;
                                }}
                            }}
                        }} catch (e) {{
                            console.error('Error in position tracking:', e);
                        }}
                    }}, 1000);
                }}
                
                // Save button handler
                saveButton.addEventListener('click', function() {{
                    if (channelConnected && backendObj) {{
                        try {{
                            backendObj.onTimeUpdate(currentTime);
                            backendObj._save_position();
                            statusElement.textContent = `Position saved: ${{formatTime(currentTime)}}`;
                            
                            // Visual feedback
                            saveButton.textContent = '✓ Saved';
                            setTimeout(() => {{
                                saveButton.textContent = 'Save Position';
                            }}, 2000);
                        }} catch (e) {{
                            statusElement.textContent = `Error saving position: ${{e.message}}`;
                            console.error('Save position error:', e);
                        }}
                    }} else {{
                        statusElement.textContent = 'Backend not available for saving (trying to reconnect)';
                        console.error('Backend connection status:', channelConnected);
                        console.error('Backend object:', backendObj);
                        
                        // Reset connection attempts to try again
                        connectionAttempts = 0;
                        setTimeout(connectToBackend, 500);
                    }}
                }});
                
                // Load YouTube API
                if (!window.YT) {{
                    var tag = document.createElement('script');
                    tag.src = "https://www.youtube.com/iframe_api";
                    var firstScriptTag = document.getElementsByTagName('script')[0];
                    firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);
                }} else {{
                    onYouTubeIframeAPIReady();
                }}
                
                // Initialize when page is loaded
                document.addEventListener('DOMContentLoaded', function() {{
                    // Ensure we have current time
                    if (typeof currentTime === 'undefined' || currentTime < 0) {{
                        currentTime = {target_position};
                    }}
                    currentTimeDisplay.textContent = formatTime(currentTime);
                    
                    // Try to connect to backend
                    setTimeout(connectToBackend, 500);
                }});
                
                // Make first connection attempt immediately
                connectToBackend();
                
                // Start position tracking as fallback after a delay
                setTimeout(function() {{
                    if (!window.positionInterval) {{
                        startPositionTracking();
                    }}
                }}, 2000);
                
                // Save position before unloading
                window.onbeforeunload = function() {{
                    if (channelConnected && backendObj) {{
                        try {{
                            backendObj.onTimeUpdate(currentTime);
                            backendObj._save_position();
                            console.log('Final position saved:', currentTime);
                        }} catch (e) {{
                            console.error('Error saving final position:', e);
                        }}
                    }}
                }};
            </script>
        </body>
        </html>
        """
        
        # Load the HTML content
        webview.setHtml(youtube_html)
        
        # Add debug JavaScript
        debug_js = """
        (function() {
            var results = {
                hasQt: typeof qt !== 'undefined',
                hasQtWebChannel: typeof QWebChannel !== 'undefined',
                hasTransport: typeof qt !== 'undefined' && qt.webChannelTransport !== undefined,
                hasBackend: typeof window.backend !== 'undefined',
                statusElement: document.getElementById('status') ? document.getElementById('status').textContent : 'No status element'
            };
            
            // List all methods on backend
            if (typeof qt !== 'undefined' && qt.webChannelTransport) {
                try {
                    new QWebChannel(qt.webChannelTransport, function(channel) {
                        if (channel && channel.objects && channel.objects.backend) {
                            results.backendMethods = [];
                            for (var prop in channel.objects.backend) {
                                if (typeof channel.objects.backend[prop] === 'function') {
                                    results.backendMethods.push(prop);
                                }
                            }
                        }
                    });
                } catch (e) {
                    results.error = e.message;
                }
            }
            
            return JSON.stringify(results);
        })();
        """
        webview.loadFinished.connect(lambda ok: webview.page().runJavaScript(debug_js))
        
        return True, callback
        
    except Exception as e:
        logger.exception(f"Error setting up YouTube WebChannel: {e}")
        return False, None

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
        
        # Create mock document and session
        self.db_session = MockSession()
        self.document = Doc(
            id=1, 
            title='Test Video',
            file_path='',
            position=30,  # Start at 30 seconds
            source_url='https://www.youtube.com/watch?v=dQw4w9WgXcQ'
        )
        
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
        
        # Set up custom logger
        self.setup_logger()
        
        # Setup the video
        self.setup_video()
        
        # Timer to simulate playback
        self.timer = QTimer(self)
        self.timer.setInterval(1000)  # 1 second
        self.timer.timeout.connect(self.update_status)
        self.timer.start()
        
        # Current time counter
        self.current_time = 0
    
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
                # Save button style before
                self.status_label.setStyleSheet("background-color: #FFFFE0;")
                self.status_label.setText("Saving position...")
                
                # Call save
                self.callback.savePosition()
                
                # Update UI with success
                logger.info(f"Position saved: {self.callback.current_position:.1f}s")
                self.status_label.setStyleSheet("background-color: #E0FFE0;")
                self.status_label.setText(f"Position saved: {self.callback.current_position:.1f}s")
                
                # Reset style after a delay
                QTimer.singleShot(2000, lambda: self.status_label.setStyleSheet(""))
            except Exception as e:
                logger.exception(f"Error saving position: {e}")
                self.status_label.setStyleSheet("background-color: #FFE0E0;")
                self.status_label.setText(f"Error saving position: {str(e)}")
        else:
            logger.warning("Callback not available")
            self.status_label.setText("Callback not available")
    
    def restart_video(self):
        """Restart the video with stored position"""
        # Create a new document with the updated position
        current_position = self.document.position if hasattr(self.document, 'position') else 0
        self.document = Doc(
            id=1,
            title='Test Video',
            file_path='',
            position=current_position,
            source_url='https://www.youtube.com/watch?v=dQw4w9WgXcQ'
        )
        
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
            
            // List all methods on backend
            if (typeof qt !== 'undefined' && qt.webChannelTransport) {
                try {
                    new QWebChannel(qt.webChannelTransport, function(channel) {
                        if (channel && channel.objects && channel.objects.backend) {
                            results.backendMethods = [];
                            for (var prop in channel.objects.backend) {
                                if (typeof channel.objects.backend[prop] === 'function') {
                                    results.backendMethods.push(prop);
                                }
                            }
                        }
                    });
                } catch (e) {
                    results.error = e.message;
                }
            }
            
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
                self.callback.savePosition()
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