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
import time
from datetime import datetime

from PyQt6.QtCore import QUrl, QTimer, Qt, QObject, pyqtSlot
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebChannel import QWebChannel
    from PyQt6.QtWidgets import QLineEdit
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False

logger = logging.getLogger(__name__)

class EnhancedYouTubeCallback(QObject):
    """Class to handle callbacks from JavaScript in the YouTube player."""
    
    def __init__(self, parent=None, current_position=0):
        super().__init__(parent)
        self.document = None
        self.db_session = None
        self.current_position = current_position
        self.video_duration = 0
        self.last_save_position = 0
        self.player_state = -1
        
        # Auto-save timer
        self.auto_save_timer = QTimer(self)
        self.auto_save_timer.setInterval(5000)  # 5 seconds
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
    
    @pyqtSlot(int)
    def onTimeUpdate(self, position):
        """Handle time update event from JavaScript.
        
        Args:
            position (int): Current playback position in seconds.
        """
        try:
            self.current_position = position
        except Exception as e:
            print(f"Error updating time: {e}")
    
    @pyqtSlot(int)
    def onDurationChange(self, duration):
        """Handle duration change event from JavaScript.
        
        Args:
            duration (int): Video duration in seconds.
        """
        try:
            self.video_duration = duration
        except Exception as e:
            print(f"Error updating duration: {e}")
    
    @pyqtSlot(int)
    def onPlayerStateChange(self, state):
        """Handle player state change event from JavaScript.
        
        Args:
            state (int): Player state code.
        """
        try:
            self.player_state = state
        except Exception as e:
            print(f"Error updating player state: {e}")
    
    @pyqtSlot()
    def savePosition(self):
        """Save the current position to the document."""
        try:
            if self.document and self.db_session:
                # Only save if position has changed significantly (5+ seconds)
                if abs(self.current_position - self.last_save_position) >= 5:
                    # Update document's position
                    self.document.position = self.current_position
                    self.document.last_modified = datetime.now()
                    
                    # Save to database
                    self.db_session.commit()
                    
                    # Update last saved position
                    self.last_save_position = self.current_position
                    
                    return True
            return False
        except Exception as e:
            print(f"Error saving position: {e}")
            return False
    
    def autoSavePosition(self):
        """Auto-save position if needed."""
        try:
            # Only save if position has changed significantly (30+ seconds)
            if abs(self.current_position - self.last_save_position) >= 30:
                self.savePosition()
        except Exception as e:
            print(f"Error in auto-save: {e}")
            
    def __del__(self):
        """Clean up when object is deleted."""
        try:
            # Final save attempt when object is destroyed
            if self.current_position > 0 and self.last_save_position != self.current_position:
                self.savePosition()
                
            # Stop timer if it's running
            if hasattr(self, 'auto_save_timer') and self.auto_save_timer.isActive():
                self.auto_save_timer.stop()
        except:
            pass

def setup_youtube_webview(webview, document, video_id, target_position=0, db_session=None):
    """Set up a WebView to display a YouTube video.
    
    Args:
        webview: The QWebEngineView to set up
        document: The document object with metadata
        video_id: YouTube video ID
        target_position: Starting position in seconds
        db_session: Database session for saving positions
    
    Returns:
        Tuple (success: bool, callback: EnhancedYouTubeCallback): A tuple containing a success flag and the callback object
    """
    try:
        # Create YouTube callback
        callback = EnhancedYouTubeCallback(parent=webview, current_position=target_position)
        
        # Set up the callback with document and db_session
        callback.setup(document, db_session)
        
        # Create web channel to communicate with JavaScript
        channel = QWebChannel(webview.page())
        channel.registerObject("backend", callback)
        webview.page().setWebChannel(channel)
        
        # Configure settings
        settings = webview.settings()
        settings.setAttribute(settings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(settings.WebAttribute.PluginsEnabled, True)
        
        # Create video URL
        video_url = "https://www.youtube.com/embed/{0}?enablejsapi=1&origin=file://&autoplay=1&start={1}&fs=1&rel=0&modestbranding=1&controls=1&showinfo=1".format(
            video_id, target_position
        )
        
        # Document title for display
        doc_title = document.title
        
        # Build HTML content using string formatting
        html_content = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{0}</title>
    <style>
        body {{ margin: 0; padding: 0; height: 100vh; background: #000; color: #fff; font-family: Arial; }}
        .container {{ display: flex; flex-direction: column; height: 100vh; }}
        .header {{ padding: 5px 10px; background: #202020; font-size: 14px; }}
        .header h3 {{ margin: 5px 0; }}
        .video-container {{ flex: 1; position: relative; background: #000; min-height: 500px; }}
        iframe {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; border: 0; }}
        #controls {{ display: flex; justify-content: space-between; padding: 5px 10px; background: #202020; }}
        button {{ background: #3ea6ff; color: #000; border: none; padding: 5px 10px; cursor: pointer; margin-left: 5px; border-radius: 2px; }}
        #status {{ position: fixed; bottom: 0; background: rgba(0,0,0,0.7); width: 100%; padding: 3px 5px; font-size: 12px; }}
        .time-input {{ display: flex; align-items: center; }}
        input[type="number"] {{ width: 60px; padding: 3px 5px; background: #333; color: white; border: 1px solid #555; }}
    </style>
    <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h3>{0}</h3>
        </div>
        <div class="video-container">
            <iframe id="player" src="{1}" allowfullscreen allow="autoplay; encrypted-media"></iframe>
        </div>
        <div id="controls">
            <div>Position: <span id="time">{2}</span></div>
            <div class="time-input">
                <input type="number" id="time-input" placeholder="Time in seconds" min="0" value="{2}">
                <button id="seek-btn">Seek</button>
                <button id="save-btn">Save Position</button>
            </div>
        </div>
        <div id="status">Loading...</div>
    </div>
    
    <script>
        // Basic variables
        var currentTime = {2};
        var backend = null;
        var player = document.getElementById('player');
        
        // DOM elements
        var timeDisplay = document.getElementById('time');
        var timeInput = document.getElementById('time-input');
        var seekButton = document.getElementById('seek-btn');
        var saveButton = document.getElementById('save-btn');
        var statusEl = document.getElementById('status');
        
        // Format time display
        function formatTime(seconds) {{
            var min = Math.floor(seconds / 60);
            var sec = Math.floor(seconds % 60);
            return min + ':' + (sec < 10 ? '0' : '') + sec;
        }}
        
        // Update time display
        function updateTimeDisplay() {{
            timeDisplay.textContent = formatTime(currentTime);
        }}
        
        // Connect to backend
        function connectBackend() {{
            if (typeof QWebChannel === 'undefined') {{
                statusEl.textContent = 'QWebChannel not available';
                setTimeout(connectBackend, 1000);
                return;
            }}
            
            try {{
                new QWebChannel(qt.webChannelTransport, function(channel) {{
                    backend = channel.objects.backend;
                    if (backend) {{
                        statusEl.textContent = 'Connected to backend';
                        startTracking();
                    }} else {{
                        statusEl.textContent = 'Backend not found';
                        setTimeout(connectBackend, 1000);
                    }}
                }});
            }} catch (e) {{
                statusEl.textContent = 'Connection error';
                setTimeout(connectBackend, 1000);
            }}
        }}
        
        // Start position tracking
        function startTracking() {{
            // Update time every second
            setInterval(function() {{
                currentTime++;
                updateTimeDisplay();
                
                if (backend && backend.onTimeUpdate) {{
                    backend.onTimeUpdate(currentTime);
                }}
            }}, 1000);
        }}
        
        // Save position
        function savePosition() {{
            if (backend && backend.savePosition) {{
                try {{
                    backend.savePosition();
                    statusEl.textContent = 'Position saved';
                    
                    // Visual feedback
                    saveButton.textContent = '✓ Saved';
                    setTimeout(function() {{
                        saveButton.textContent = 'Save Position';
                    }}, 2000);
                }} catch (e) {{
                    statusEl.textContent = 'Error saving position';
                }}
            }}
        }}
        
        // Seek to time
        function seekToTime() {{
            var time = parseInt(timeInput.value, 10);
            if (isNaN(time) || time < 0) {{
                statusEl.textContent = 'Invalid time value';
                return;
            }}
            
            try {{
                // Update iframe URL with new start time
                var iframe = document.getElementById('player');
                var src = iframe.src;
                var newSrc = src.replace(/(&start=)\\d+/, '$1' + time);
                if (src === newSrc) {{
                    // If no start parameter exists, add it
                    if (src.indexOf('?') !== -1) {{
                        newSrc = src + '&start=' + time;
                    }} else {{
                        newSrc = src + '?start=' + time;
                    }}
                }}
                iframe.src = newSrc;
                
                // Update current time
                currentTime = time;
                updateTimeDisplay();
                
                // Update backend
                if (backend && backend.onTimeUpdate) {{
                    backend.onTimeUpdate(currentTime);
                }}
                
                statusEl.textContent = 'Seeking to ' + formatTime(time);
            }} catch (e) {{
                statusEl.textContent = 'Error seeking: ' + e.message;
            }}
        }}
        
        // Initialize
        updateTimeDisplay();
        saveButton.addEventListener('click', savePosition);
        seekButton.addEventListener('click', seekToTime);
        connectBackend();
        
        // Save on unload
        window.onbeforeunload = function() {{
            if (backend && backend.savePosition) {{
                backend.savePosition();
            }}
        }};
    </script>
</body>
</html>""".format(doc_title, video_url, target_position)

        # Load the content
        webview.setHtml(html_content, QUrl("https://www.youtube.com/"))
        
        # Return success and the callback object
        return True, callback
        
    except Exception as e:
        print("Error setting up YouTube webview: %s" % e)
        return False, None

def extract_video_id_from_document(document):
    """Extract YouTube video ID from document metadata or URL."""
    video_id = None
    
    try:
        # Method 1: From JSON metadata file
        if hasattr(document, 'file_path') and document.file_path and os.path.exists(document.file_path):
            if document.file_path.endswith('.json'):
                with open(document.file_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    video_id = metadata.get('video_id')
        
        # Method 2: From document properties
        if not video_id and hasattr(document, 'video_id'):
            video_id = document.video_id
            
        # Method 3: From source_url
        if not video_id and hasattr(document, 'source_url') and document.source_url:
            from core.document_processor.handlers.youtube_handler import YouTubeHandler
            handler = YouTubeHandler()
            video_id = handler._extract_video_id(document.source_url)
            
        # Method 4: From file_path if it's a URL
        if not video_id and hasattr(document, 'file_path') and document.file_path:
            if document.file_path.startswith('http'):
                from core.document_processor.handlers.youtube_handler import YouTubeHandler
                handler = YouTubeHandler()
                video_id = handler._extract_video_id(document.file_path)
    
    except Exception as e:
        logger.exception(f"Error extracting YouTube video ID: {e}")
    
    return video_id

def create_youtube_player_html(document, video_id, target_position):
    """Generate HTML for the YouTube player with improved position tracking."""
    # Format document information for display
    title = getattr(document, 'title', 'YouTube Video')
    author = getattr(document, 'author', 'Unknown author')
    
    # Base HTML template
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{title}</title>
        <style>
            body {{ margin: 0; padding: 0; background: #000; color: #fff; font-family: Arial; height: 100vh; overflow: hidden; }}
            .container {{ display: flex; flex-direction: column; height: 100vh; }}
            .header {{ padding: 10px; background: #202020; }}
            .video-container {{ 
                flex: 1; 
                display: flex;
                align-items: center;
                justify-content: center;
                overflow: hidden;
                background: #000;
                position: relative;
            }}
            #youtube-player {{
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
            }}
            #controls {{ display: flex; justify-content: space-between; padding: 10px; background: #202020; }}
            button {{ background: #3ea6ff; color: black; border: none; padding: 8px 15px; cursor: pointer; margin-left: 5px; }}
            #status {{ position: fixed; bottom: 0; background: rgba(0,0,0,0.7); width: 100%; padding: 5px; }}
            .time-input {{ display: flex; align-items: center; }}
            input[type="number"] {{ width: 60px; padding: 5px; background: #333; color: white; border: 1px solid #555; }}
        </style>
        <!-- Load Qt WebChannel library to connect with Python -->
        <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>{title}</h1>
                <p>{author}</p>
            </div>
            
            <div class="video-container" id="player-container">
                <!-- YouTube player will be inserted here -->
                <div id="youtube-player"></div>
            </div>
            
            <div id="controls">
                <div class="time-display">
                    <span id="current-time">0:00</span> / <span id="duration">0:00</span>
                </div>
                <div class="time-input">
                    <input type="number" id="time-input" placeholder="Time in seconds" min="0" value="{target_position}">
                    <button id="seek-btn">Seek</button>
                    <button id="save-position" class="button">Save Position</button>
                </div>
            </div>
            
            <div id="status">Loading player...</div>
        </div>
        
        <script>
            // Initial variables
            let player = null;
            let playerReady = false;
            let currentTime = {target_position};
            let duration = 0;
            let statusElement = document.getElementById('status');
            let currentTimeDisplay = document.getElementById('current-time');
            let durationDisplay = document.getElementById('duration');
            let timeInput = document.getElementById('time-input');
            let seekButton = document.getElementById('seek-btn');
            let saveButton = document.getElementById('save-position');
            let backendObj = null;
            let channelConnected = false;
            let timeUpdateInterval = null;
            
            // Load YouTube API
            var tag = document.createElement('script');
            tag.src = "https://www.youtube.com/iframe_api";
            tag.onerror = function() {{
                console.error("Failed to load YouTube iframe API - using iframe fallback");
                createFallbackPlayer();
            }};
            var firstScriptTag = document.getElementsByTagName('script')[0];
            firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);
            
            // Format time as MM:SS
            function formatTime(seconds) {{
                if (seconds === undefined || seconds === null) return '0:00';
                seconds = Math.round(seconds);
                const minutes = Math.floor(seconds / 60);
                seconds = seconds % 60;
                return minutes + ':' + (seconds < 10 ? '0' : '') + seconds;
            }}
            
            // Initialize YouTube player when API is ready
            function onYouTubeIframeAPIReady() {{
                console.log("YouTube API ready, creating player...");
                
                player = new YT.Player('youtube-player', {{
                    videoId: '{video_id}',
                    playerVars: {{
                        'autoplay': 1,
                        'start': {target_position},
                        'enablejsapi': 1,
                        'rel': 0,
                        'fs': 1,
                        'modestbranding': 1,
                        'origin': window.location.origin || 'file://'
                    }},
                    events: {{
                        'onReady': onPlayerReady,
                        'onStateChange': onPlayerStateChange,
                        'onError': onPlayerError
                    }}
                }});
            }}
            
            // Player ready event handler
            function onPlayerReady(event) {{
                console.log("Player ready!");
                playerReady = true;
                statusElement.textContent = 'Player ready';
                
                // Get initial duration
                try {{
                    duration = player.getDuration();
                    durationDisplay.textContent = formatTime(duration);
                    
                    // Update backend with duration
                    if (backendObj && backendObj.onDurationChange) {{
                        backendObj.onDurationChange(duration);
                    }}
                }} catch (e) {{
                    console.error("Error getting duration:", e);
                }}
                
                // Start time tracking interval
                startTimeTracking();
            }}
            
            // Player state change event handler
            function onPlayerStateChange(event) {{
                console.log("Player state changed:", event.data);
                
                // Update backend with player state
                if (backendObj && backendObj.onPlayerStateChange) {{
                    backendObj.onPlayerStateChange(event.data);
                }}
                
                // If video is paused or ended, update and save position
                if (event.data === YT.PlayerState.PAUSED || event.data === YT.PlayerState.ENDED) {{
                    updateCurrentTime();
                    
                    // Save position if backend connected
                    if (backendObj && backendObj.savePosition) {{
                        backendObj.savePosition();
                        statusElement.textContent = 'Position saved (video ' + 
                            (event.data === YT.PlayerState.PAUSED ? 'paused' : 'ended') + ')';
                    }}
                }}
            }}
            
            // Player error event handler
            function onPlayerError(event) {{
                console.error("Player error:", event.data);
                statusElement.textContent = 'Player error: ' + event.data;
                
                // If API fails, try fallback
                if (!playerReady) {{
                    createFallbackPlayer();
                }}
            }}
            
            // Start tracking player time
            function startTimeTracking() {{
                // Clear any existing interval
                if (timeUpdateInterval) {{
                    clearInterval(timeUpdateInterval);
                }}
                
                // Update time every 500ms
                timeUpdateInterval = setInterval(function() {{
                    updateCurrentTime();
                }}, 500);
            }}
            
            // Update current time from player
            function updateCurrentTime() {{
                if (!player || !playerReady) return;
                
                try {{
                    // Get current time from player
                    currentTime = player.getCurrentTime();
                    
                    // Update display
                    currentTimeDisplay.textContent = formatTime(currentTime);
                    
                    // Update backend
                    if (backendObj && backendObj.onTimeUpdate) {{
                        backendObj.onTimeUpdate(currentTime);
                    }}
                    
                    // Update input value
                    timeInput.value = Math.round(currentTime);
                }} catch (e) {{
                    console.error("Error getting current time:", e);
                }}
            }}
            
            // Seek to specific time (manual input)
            function seekToTime() {{
                let time = parseInt(timeInput.value, 10);
                if (isNaN(time) || time < 0) {{
                    statusElement.textContent = 'Invalid time value';
                    return;
                }}
                
                try {{
                    if (player && playerReady) {{
                        // Use YouTube API's seekTo method
                        player.seekTo(time, true);
                        statusElement.textContent = 'Seeking to ' + formatTime(time);
                        
                        // Update current time
                        currentTime = time;
                        currentTimeDisplay.textContent = formatTime(time);
                        
                        // Update backend
                        if (backendObj && backendObj.onTimeUpdate) {{
                            backendObj.onTimeUpdate(time);
                        }}
                    }} else {{
                        // Fallback for when player API isn't available
                        statusElement.textContent = 'Player not ready, using fallback seeking method';
                        fallbackSeek(time);
                    }}
                }} catch (e) {{
                    console.error("Error seeking:", e);
                    statusElement.textContent = 'Error seeking: ' + e.message;
                    fallbackSeek(time);
                }}
            }}
            
            // Fallback seek method (recreate player)
            function fallbackSeek(time) {{
                const container = document.getElementById('player-container');
                // Clean container
                container.innerHTML = '<div id="youtube-player"></div>';
                
                // Try to recreate player at new position
                if (typeof YT !== 'undefined' && YT.Player) {{
                    player = new YT.Player('youtube-player', {{
                        videoId: '{video_id}',
                        playerVars: {{
                            'autoplay': 1,
                            'start': time,
                            'enablejsapi': 1,
                            'rel': 0,
                            'fs': 1,
                            'modestbranding': 1
                        }},
                        events: {{
                            'onReady': onPlayerReady,
                            'onStateChange': onPlayerStateChange,
                            'onError': onPlayerError
                        }}
                    }});
                }} else {{
                    // If API not available, use iframe fallback
                    container.innerHTML = '';
                    const iframe = document.createElement('iframe');
                    iframe.id = 'player';
                    iframe.width = '100%';
                    iframe.height = '100%';
                    iframe.src = 'https://www.youtube.com/embed/{video_id}?autoplay=1&start=' + time + '&rel=0&fs=1&modestbranding=1';
                    iframe.frameBorder = '0';
                    iframe.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture';
                    iframe.allowFullscreen = true;
                    container.appendChild(iframe);
                    
                    // Start basic tracking for fallback
                    startBasicTracking();
                }}
                
                // Update current time and display
                currentTime = time;
                currentTimeDisplay.textContent = formatTime(time);
                
                // Update backend
                if (backendObj && backendObj.onTimeUpdate) {{
                    backendObj.onTimeUpdate(time);
                }}
            }}
            
            // Fallback: directly create an iframe if the API fails to load
            function createFallbackPlayer() {{
                const container = document.getElementById('player-container');
                
                // Clear any existing content
                container.innerHTML = '';
                
                // Create iframe directly
                const iframe = document.createElement('iframe');
                iframe.id = 'player';
                iframe.width = '100%';
                iframe.height = '100%';
                iframe.src = 'https://www.youtube.com/embed/{video_id}?autoplay=1&start={target_position}&rel=0&fs=1&modestbranding=1';
                iframe.frameBorder = '0';
                iframe.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture';
                iframe.allowFullscreen = true;
                
                // Add to container
                container.appendChild(iframe);
                
                // Start basic tracking
                startBasicTracking();
                statusElement.textContent = 'Using fallback player (limited functionality)';
            }}
            
            // Basic tracking for fallback player
            function startBasicTracking() {{
                // Clear any existing interval
                if (timeUpdateInterval) {{
                    clearInterval(timeUpdateInterval);
                }}
                
                timeUpdateInterval = setInterval(function() {{
                    // Simple increment of time
                    currentTime += 0.5;  // 500ms interval = 0.5s per update
                    currentTimeDisplay.textContent = formatTime(currentTime);
                    
                    // Update backend if connected
                    if (channelConnected && backendObj) {{
                        try {{
                            backendObj.onTimeUpdate(currentTime);
                        }} catch (e) {{
                            console.error('Error updating time:', e);
                        }}
                    }}
                }}, 500);
            }}
            
            // Connect to backend via WebChannel
            function connectToBackend() {{
                if (typeof QWebChannel === 'undefined') {{
                    statusElement.textContent = 'QWebChannel not available, retrying...';
                    setTimeout(connectToBackend, 1000);
                    return;
                }}
                
                try {{
                    new QWebChannel(qt.webChannelTransport, function(channel) {{
                        backendObj = channel.objects.backend;
                        if (backendObj) {{
                            channelConnected = true;
                            statusElement.textContent = 'Connected to backend';
                            
                            // Send initial time
                            if (backendObj.onTimeUpdate) {{
                                backendObj.onTimeUpdate(currentTime);
                            }}
                            
                            // Send initial duration if available
                            if (duration > 0 && backendObj.onDurationChange) {{
                                backendObj.onDurationChange(duration);
                            }}
                        }} else {{
                            statusElement.textContent = 'Backend object not found, retrying...';
                            setTimeout(connectToBackend, 1000);
                        }}
                    }});
                }} catch (e) {{
                    console.error('WebChannel error:', e);
                    statusElement.textContent = 'Connection error, retrying...';
                    setTimeout(connectToBackend, 1000);
                }}
            }}
            
            // Manual save position
            function saveCurrentPosition() {{
                if (backendObj && backendObj.savePosition) {{
                    // Update current time first if player is available
                    if (player && playerReady) {{
                        try {{
                            currentTime = player.getCurrentTime();
                            
                            // Update backend time
                            if (backendObj.onTimeUpdate) {{
                                backendObj.onTimeUpdate(currentTime);
                            }}
                        }} catch (e) {{
                            console.error("Error getting current time for save:", e);
                        }}
                    }}
                    
                    // Save position
                    backendObj.savePosition();
                    statusElement.textContent = 'Position saved';
                    
                    // Visual feedback
                    saveButton.textContent = '✓ Saved';
                    setTimeout(function() {{
                        saveButton.textContent = 'Save Position';
                    }}, 2000);
                }} else {{
                    statusElement.textContent = 'Cannot save: backend not connected';
                }}
            }}
            
            // Initialize connections and event listeners
            connectToBackend();
            
            // Add event listeners
            if (saveButton) {{
                saveButton.addEventListener('click', saveCurrentPosition);
            }}
            
            // Add seek button event listener
            if (seekButton) {{
                seekButton.addEventListener('click', seekToTime);
            }}
            
            // Handle page unload - save position
            window.addEventListener('beforeunload', function() {{
                if (backendObj && backendObj.savePosition) {{
                    // Update current time first
                    if (player && playerReady) {{
                        try {{
                            currentTime = player.getCurrentTime();
                            backendObj.onTimeUpdate(currentTime);
                        }} catch (e) {{
                            console.error("Error updating time on unload:", e);
                        }}
                    }}
                    
                    // Save position
                    backendObj.savePosition();
                }}
            }});
            
            // Set a timeout to use fallback if API doesn't load quickly
            setTimeout(function() {{
                if (!player || !playerReady) {{
                    console.warn("YouTube API took too long to load, using fallback");
                    createFallbackPlayer();
                }}
            }}, 5000);
        </script>
    </body>
    </html>
    """
    
    return html


def add_debugging_tools(webview):
    """Add debugging tools to help troubleshoot WebChannel issues."""
    # JavaScript for debugging WebChannel communication
    debug_js = """
    (function() {
        console.log('Adding diagnostic tools...');
        
        // Create a debug panel
        var debugPanel = document.createElement('div');
        debugPanel.id = 'debug-panel';
        debugPanel.style.position = 'fixed';
        debugPanel.style.right = '10px';
        debugPanel.style.top = '10px';
        debugPanel.style.background = 'rgba(0,0,0,0.7)';
        debugPanel.style.color = 'white';
        debugPanel.style.padding = '10px';
        debugPanel.style.borderRadius = '5px';
        debugPanel.style.fontSize = '12px';
        debugPanel.style.zIndex = '10000';
        debugPanel.style.maxWidth = '300px';
        debugPanel.style.maxHeight = '200px';
        debugPanel.style.overflow = 'auto';
        debugPanel.style.display = 'none';
        
        // Create toggle button
        var debugButton = document.createElement('button');
        debugButton.textContent = 'Debug';
        debugButton.style.position = 'fixed';
        debugButton.style.right = '10px';
        debugButton.style.top = '10px';
        debugButton.style.zIndex = '10001';
        debugButton.style.padding = '5px';
        debugButton.style.background = '#555';
        debugButton.style.color = 'white';
        debugButton.style.border = 'none';
        debugButton.style.borderRadius = '3px';
        debugButton.style.opacity = '0.7';
        debugButton.style.cursor = 'pointer';
        
        // Toggle debug panel
        debugButton.onclick = function() {
            if (debugPanel.style.display === 'none') {
                debugPanel.style.display = 'block';
                updateDebugInfo();
            } else {
                debugPanel.style.display = 'none';
            }
        };
        
        // Add elements to the document
        document.body.appendChild(debugPanel);
        document.body.appendChild(debugButton);
        
        // Function to update debug information
        function updateDebugInfo() {
            if (debugPanel.style.display === 'none') return;
            
            var info = '';
            info += '<strong>WebChannel:</strong> ' + (typeof QWebChannel !== 'undefined' ? 'Available' : 'Missing') + '<br>';
            info += '<strong>Backend:</strong> ' + (channelConnected ? 'Connected' : 'Disconnected') + '<br>';
            
            if (player) {
                try {
                    info += '<strong>Player:</strong> ' + (playerReady ? 'Ready' : 'Not ready') + '<br>';
                    info += '<strong>Current time:</strong> ' + player.getCurrentTime() + 's<br>';
                    info += '<strong>Duration:</strong> ' + player.getDuration() + 's<br>';
                    info += '<strong>State:</strong> ' + player.getPlayerState() + '<br>';
                    
                    // Get video quality
                    var quality = player.getPlaybackQuality();
                    info += '<strong>Quality:</strong> ' + quality + '<br>';
                    
                    // Get buffered percentage
                    var buffered = player.getVideoLoadedFraction() * 100;
                    info += '<strong>Buffered:</strong> ' + buffered.toFixed(1) + '%<br>';
                } catch(e) {
                    info += '<strong>Player error:</strong> ' + e.message + '<br>';
                }
            } else {
                info += '<strong>Player:</strong> Not initialized<br>';
            }
            
            // Add backend status if available
            if (backendObj && typeof backendObj.getStatus === 'function') {
                try {
                    backendObj.getStatus(function(status) {
                        if (status) {
                            info += '<hr><strong>Backend status:</strong><br>';
                            for (var key in status) {
                                info += '<strong>' + key + ':</strong> ' + status[key] + '<br>';
                            }
                            debugPanel.innerHTML = info;
                        }
                    });
                } catch(e) {
                    info += '<strong>Backend error:</strong> ' + e.message + '<br>';
                    debugPanel.innerHTML = info;
                }
            } else {
                debugPanel.innerHTML = info;
            }
            
            // Update every second
            setTimeout(updateDebugInfo, 1000);
        }
    })();
    """
    
    # Add the debug tools when the page is loaded
    webview.loadFinished.connect(lambda ok: webview.page().runJavaScript(debug_js))