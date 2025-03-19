# ui/load_youtube_helper.py
#
# This module provides YouTube video embedding with position tracking for Incrementum.
#
# Key fixes to make WebChannel communication reliable:
# 1. Use qrc:///qtwebchannel/qwebchannel.js script reference to load Qt's WebChannel library
# 2. Ensure the WebChannel is set up BEFORE loading the HTML content
# 3. Connect to the WebChannel with multiple retry attempts 
# 4. Use more robust error handling in JavaScript for corner cases
# 5. Add manual Save button as a reliable fallback
# 6. Check for connection status before attempting to use the backend
# 7. Auto-save position when position changes significantly (>3 seconds)
# 8. Add visual feedback to confirm saving works

import os
import logging
import json
from typing import Optional

from PyQt6.QtCore import QUrl, QTimer, Qt, QObject, pyqtSlot
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebChannel import QWebChannel
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False

logger = logging.getLogger(__name__)

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
        self.auto_save_timer.timeout.connect(self.autoSavePosition)
    
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
            self.savePosition()
    
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
    
    @pyqtSlot()
    def autoSavePosition(self):
        """Automatically save position periodically."""
        # Only save if position has changed significantly
        if self.document and self.current_position > 0:
            # Only save if position changed by more than 3 seconds
            if abs(self.current_position - self.last_save_position) > 3:
                self.savePosition()
    
    @pyqtSlot()
    def savePosition(self):
        """Save the current position to the database."""
        if not self.document or not self.db_session:
            return
        
        # Don't save if position is at the very beginning (0) or the same as last saved
        if self.current_position <= 0 or self.current_position == self.last_save_position:
            return
        
        try:
            # Store position in seconds
            self.document.position = int(self.current_position)
            self.db_session.commit()
            self.last_save_position = self.current_position
            logger.debug(f"Saved YouTube position: {self.current_position:.1f}s for {self.document.title}")
        except Exception as e:
            logger.exception(f"Error saving YouTube position: {e}")

def setup_youtube_webview(document, webview, db_session, restore_position=True):
    """
    Set up YouTube player in a WebView with position tracking.
    
    Args:
        document: The Document object being displayed
        webview: The QWebEngineView instance
        db_session: Database session
        restore_position: Whether to restore the position
        
    Returns:
        tuple: (success status, YouTube callback object)
    """
    if not HAS_WEBENGINE or not isinstance(webview, QWebEngineView):
        return False, None
    
    # Extract video ID from metadata or file path
    video_id = None
    try:
        if hasattr(document, 'file_path') and document.file_path:
            # If it's a metadata file, read it to get video ID
            if os.path.exists(document.file_path) and document.file_path.endswith('.json'):
                with open(document.file_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    video_id = metadata.get('video_id')
            # Try to extract from the URL directly
            elif document.file_path.startswith('http'):
                from core.document_processor.handlers.youtube_handler import YouTubeHandler
                handler = YouTubeHandler()
                video_id = handler._extract_video_id(document.file_path)
        
        # If we still don't have an ID, try to get it from source_url
        if not video_id and hasattr(document, 'source_url') and document.source_url:
            from core.document_processor.handlers.youtube_handler import YouTubeHandler
            handler = YouTubeHandler()
            video_id = handler._extract_video_id(document.source_url)
    except Exception as e:
        logger.exception(f"Error extracting YouTube video ID: {e}")
    
    if not video_id:
        logger.error(f"Could not determine YouTube video ID for document: {document.id}")
        return False, None
    
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
                
                // Update position periodically
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
                            backendObj.savePosition();
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
                            backendObj.savePosition();
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
            console.log('WebChannel objects available:', qt);
            if (typeof QWebChannel !== 'undefined') {
                console.log('QWebChannel is available');
            } else {
                console.log('QWebChannel is NOT available');
            }
            
            // Debug backend object methods
            if (typeof qt !== 'undefined' && qt.webChannelTransport) {
                new QWebChannel(qt.webChannelTransport, function(channel) {
                    if (channel && channel.objects && channel.objects.backend) {
                        var methods = [];
                        for (var prop in channel.objects.backend) {
                            if (typeof channel.objects.backend[prop] === 'function') {
                                methods.push(prop);
                            }
                        }
                        console.log('Available methods on backend:', methods);
                    }
                });
            }
            
            // Add error handling for WebChannel
            window.addEventListener('error', function(event) {
                console.error('Caught JS error:', event.error);
                var status = document.getElementById('status');
                if (status) {
                    status.textContent = 'JS Error: ' + event.error.message;
                    status.style.color = 'red';
                }
            });
            
            // Patch QWebChannel to catch callback errors
            if (typeof QWebChannel !== 'undefined') {
                var origExec = QWebChannel.prototype.__proto__.exec;
                if (origExec) {
                    QWebChannel.prototype.__proto__.exec = function(data, callback) {
                        try {
                            return origExec.call(this, data, callback);
                        } catch (e) {
                            console.error('QWebChannel exec error:', e);
                            var status = document.getElementById('status');
                            if (status) {
                                status.textContent = 'Channel Error: ' + e.message;
                                status.style.color = 'red';
                            }
                            return false;
                        }
                    };
                }
            }
            
            // Check if element is there
            var status = document.getElementById('status');
            if (status) {
                status.textContent += ' (Debug: JS executed)';
            }
        })();
        """
        webview.loadFinished.connect(lambda ok: webview.page().runJavaScript(debug_js))
        
        return True, callback
        
    except Exception as e:
        logger.exception(f"Error setting up YouTube WebChannel: {e}")
        return False, None 