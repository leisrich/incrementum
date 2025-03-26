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
        
        # For playlist support
        self.playlist_video = None
        self.is_playlist = False
        
        # Auto-save timer
        self.auto_save_timer = QTimer(self)
        self.auto_save_timer.setInterval(5000)  # 5 seconds
        self.auto_save_timer.timeout.connect(self.autoSavePosition)
    
    def setup(self, document, db_session, playlist_video=None):
        """Set up the callback with document and database session.
        
        Args:
            document: Document object
            db_session: Database session
            playlist_video: YouTubePlaylistVideo object for playlist support
        """
        self.document = document
        self.db_session = db_session
        self.auto_save_timer.start()
        
        # Initialize with last known position
        if hasattr(document, 'position') and document.position:
            self.current_position = document.position
            self.last_save_position = document.position
            
        # Set up playlist support if available
        if playlist_video:
            self.playlist_video = playlist_video
            self.is_playlist = True
            # If playlist video has a specific position, use that instead
            if playlist_video.watched_position > 0:
                self.current_position = playlist_video.watched_position
                self.last_save_position = playlist_video.watched_position
    
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
        """Save the current position to the document and playlist if applicable."""
        try:
            if not self.db_session:
                return False
                
            should_save_doc = False
            should_save_playlist = False
            
            # Only save if position has changed significantly (5+ seconds)
            if abs(self.current_position - self.last_save_position) >= 5:
                # Update document's position
                if self.document:
                    self.document.position = self.current_position
                    self.document.last_modified = datetime.now()
                    should_save_doc = True
                
                # Update playlist video position if applicable
                if self.is_playlist and self.playlist_video:
                    self.playlist_video.watched_position = self.current_position
                    self.playlist_video.last_watched = datetime.now()
                    
                    # Calculate percentage watched
                    if self.video_duration > 0:
                        percent = (self.current_position / self.video_duration) * 100
                        self.playlist_video.watched_percent = min(100.0, percent)
                        
                        # Auto-mark as complete if >95% watched
                        if percent > 95:
                            self.playlist_video.marked_complete = True
                    
                    should_save_playlist = True
                
                # Save to database if needed
                if should_save_doc or should_save_playlist:
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

class WebViewCallback(QObject):
    """Class to handle basic callbacks from the YouTube player for compatibility."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.document_view = parent
        
    @pyqtSlot(int)
    def onTimeUpdate(self, position):
        """Handle time update event from JavaScript."""
        pass
    
    @pyqtSlot()
    def savePosition(self):
        """Save the current position."""
        pass

def setup_youtube_webview(webview, document, video_id, target_position=0, db_session=None, playlist_video=None):
    """Set up a WebView to display a YouTube video.
    
    Args:
        webview: The QWebEngineView to set up
        document: The document object with metadata
        video_id: YouTube video ID
        target_position: Starting position in seconds
        db_session: Database session for saving positions
        playlist_video: YouTubePlaylistVideo object for playlist support
    
    Returns:
        Tuple (success: bool, callback: EnhancedYouTubeCallback): A tuple containing a success flag and the callback object
    """
    try:
        # Create YouTube callback
        callback = EnhancedYouTubeCallback(parent=webview, current_position=target_position)
        
        # Set up the callback with document and db_session
        callback.setup(document, db_session, playlist_video)
        
        # Create web channel to communicate with JavaScript
        channel = QWebChannel(webview.page())
        channel.registerObject("backend", callback)
        webview.page().setWebChannel(channel)
        
        # Configure settings
        settings = webview.settings()
        settings.setAttribute(settings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(settings.WebAttribute.PluginsEnabled, True)
        
        # Check if this is part of a playlist for UI enhancements
        is_playlist = playlist_video is not None
        
        # Create video URL
        video_url = "https://www.youtube.com/embed/{0}?enablejsapi=1&origin=https://www.youtube.com&autoplay=1&start={1}&fs=1&rel=0&modestbranding=1&controls=1&showinfo=1".format(
            video_id, target_position
        )
        
        # Document title for display
        doc_title = document.title
        
        # Build HTML content with enhanced UI for playlists if needed
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
        #playlist-controls {{ display: flex; justify-content: center; padding: 5px; background: #202020; }}
        #playlist-controls button {{ margin: 0 10px; min-width: 80px; }}
        .progress-container {{ height: 5px; background: #333; width: 100%; position: relative; }}
        .progress-bar {{ height: 100%; background: #f00; width: 0%; transition: width 0.5s; }}
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
        <div class="progress-container">
            <div class="progress-bar" id="progress-bar"></div>
        </div>
""".format(doc_title, video_url)

        # Add playlist controls if this is part of a playlist
        if is_playlist:
            position = playlist_video.position
            playlist_id = playlist_video.playlist.id
            playlist_title = playlist_video.playlist.title
            
            # Enhance the HTML with playlist navigation controls
            html_content += """
        <div id="playlist-controls">
            <button id="prev-video" title="Previous Video">Previous</button>
            <span id="playlist-position" style="padding: 5px 10px;">Video {0} in playlist</span>
            <button id="next-video" title="Next Video">Next</button>
        </div>
        <div style="text-align: center; padding: 2px 5px; background: #111; font-size: 12px;">
            <span>Playlist: {1}</span>
        </div>
""".format(position, playlist_title)

        # Continue with the rest of the HTML
        html_content += """
        <div id="controls">
            <div>Position: <span id="time">{0}</span></div>
            <div class="time-input">
                <input type="number" id="time-input" placeholder="Time in seconds" min="0" value="{0}">
                <button id="seek-btn">Seek</button>
                <button id="save-btn">Save Position</button>
            </div>
        </div>
        <div id="status">Loading...</div>
    </div>
    
    <script>
        // Basic variables
        var currentTime = {0};
        var backend = null;
        var player = document.getElementById('player');
        
        // DOM elements
        var timeDisplay = document.getElementById('time');
        var timeInput = document.getElementById('time-input');
        var seekButton = document.getElementById('seek-btn');
        var saveButton = document.getElementById('save-btn');
        var statusEl = document.getElementById('status');
        var progressBar = document.getElementById('progress-bar');
""".format(target_position)

        # Add playlist-specific JavaScript if needed
        if is_playlist:
            html_content += """
        // Playlist elements
        var prevButton = document.getElementById('prev-video');
        var nextButton = document.getElementById('next-video');
        var playlistPosition = document.getElementById('playlist-position');
        
        // Playlist navigation functions
        function goToPrevVideo() {
            if (backend) {
                backend.savePosition();
                window.location.href = "playlist:{0}:{1}:prev";
            }
        }
        
        function goToNextVideo() {
            if (backend) {
                backend.savePosition();
                window.location.href = "playlist:{0}:{1}:next";
            }
        }
        
        // Set up playlist button listeners
        if (prevButton) prevButton.addEventListener('click', goToPrevVideo);
        if (nextButton) nextButton.addEventListener('click', goToNextVideo);
        
        // Handle end of video for auto-advancing to next
        function onPlayerStateChange(event) {
            if (event.data === 0) {  // Video ended (YT.PlayerState.ENDED)
                console.log("Video ended, advancing to next video");
                // Wait a moment to ensure position is saved
                setTimeout(goToNextVideo, 500);
            }
        }
""".format(playlist_id, position)

        # Continue with the rest of the JavaScript
        html_content += """
        // Update progress bar
        function updateProgressBar(currentTime, duration) {
            if (duration && duration > 0) {
                var percent = (currentTime / duration) * 100;
                progressBar.style.width = percent + '%';
            }
        }
        
        // Connect to backend
        var retryCount = 0;
        var maxRetries = 5;
        
        function connectToBackend() {
            statusEl.innerHTML = "Connecting to backend...";
            
            if (retryCount >= maxRetries) {
                statusEl.innerHTML = "Failed to connect to backend after " + maxRetries + " attempts.";
                return;
            }
            
            try {
                new QWebChannel(qt.webChannelTransport, function(channel) {
                    backend = channel.objects.backend;
                    
                    if (backend) {
                        statusEl.innerHTML = "Connected to backend. Setting up player...";
                        setupYouTubeAPI();
                    } else {
                        retryCount++;
                        statusEl.innerHTML = "Backend connection attempt " + retryCount + " failed, retrying...";
                        setTimeout(connectToBackend, 500);
                    }
                });
            } catch (e) {
                retryCount++;
                statusEl.innerHTML = "Connection error: " + e + ". Retry " + retryCount + "...";
                setTimeout(connectToBackend, 500);
            }
        }
        
        // Initialize YouTube API
        var ytPlayer = null;
        
        function setupYouTubeAPI() {
            // Function to be called when API is ready
            window.onYouTubeIframeAPIReady = function() {
                statusEl.innerHTML = "YouTube API ready, initializing player...";
                
                // Create YouTube player instance
                ytPlayer = new YT.Player('player', {
                    events: {
                        'onReady': onPlayerReady,
                        'onStateChange': onPlayerStateChange,
                        'onError': onPlayerError
                    }
                });
            };
            
            // Load YouTube iframe API
            var tag = document.createElement('script');
            tag.src = 'https://www.youtube.com/iframe_api';
            var firstScriptTag = document.getElementsByTagName('script')[0];
            firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);
        }
        
        // YouTube player event handlers
        function onPlayerReady(event) {
            statusEl.innerHTML = "Player ready.";
            
            // Connect player events for time tracking
            setupPlayerTimeTracking();
            
            // Start from saved position if there is one
            if (currentTime > 0) {
                event.target.seekTo(currentTime, true);
            }
        }
        
        function onPlayerError(event) {
            console.error("Player error: " + event.data);
            statusEl.innerHTML = "Player error: " + event.data;
        }
        
        // Set up event listeners
        seekButton.addEventListener('click', function() {
            var time = parseInt(timeInput.value);
            if (!isNaN(time) && ytPlayer) {
                ytPlayer.seekTo(time, true);
                statusEl.innerHTML = "Seeking to " + time + " seconds.";
            }
        });
        
        saveButton.addEventListener('click', function() {
            if (backend) {
                var success = backend.savePosition();
                if (success) {
                    statusEl.innerHTML = "Position saved: " + currentTime + " seconds.";
                    setTimeout(function() {
                        statusEl.innerHTML = "Ready.";
                    }, 2000);
                } else {
                    statusEl.innerHTML = "Failed to save position.";
                }
            } else {
                statusEl.innerHTML = "Backend not available.";
            }
        });
        
        // Set up time tracking
        var lastReportedTime = 0;
        var updateInterval = 1000; // Update every 1 second
        var intervalId = null;
        
        function setupPlayerTimeTracking() {
            if (intervalId) {
                clearInterval(intervalId);
            }
            
            intervalId = setInterval(function() {
                if (ytPlayer && ytPlayer.getCurrentTime) {
                    try {
                        var time = Math.floor(ytPlayer.getCurrentTime());
                        var state = ytPlayer.getPlayerState();
                        var duration = ytPlayer.getDuration();
                        
                        // Only update if time has changed
                        if (time !== lastReportedTime) {
                            lastReportedTime = time;
                            currentTime = time;
                            
                            // Update UI
                            timeDisplay.innerHTML = formatTime(time) + ' / ' + formatTime(duration);
                            timeInput.value = time;
                            
                            // Update progress bar
                            updateProgressBar(time, duration);
                            
                            // Send to backend
                            if (backend) {
                                backend.onTimeUpdate(time);
                                if (duration) {
                                    backend.onDurationChange(Math.floor(duration));
                                }
                                if (typeof state !== 'undefined') {
                                    backend.onPlayerStateChange(state);
                                }
                            }
                        }
                    } catch (e) {
                        console.error("Error getting player time: " + e);
                    }
                }
            }, updateInterval);
        }
        
        // Format time as MM:SS or HH:MM:SS
        function formatTime(seconds) {
            if (isNaN(seconds) || seconds < 0) return "00:00";
            
            var hours = Math.floor(seconds / 3600);
            var minutes = Math.floor((seconds % 3600) / 60);
            var secs = Math.floor(seconds % 60);
            
            if (hours > 0) {
                return hours + ":" + 
                       (minutes < 10 ? "0" + minutes : minutes) + ":" + 
                       (secs < 10 ? "0" + secs : secs);
            } else {
                return (minutes < 10 ? "0" + minutes : minutes) + ":" + 
                       (secs < 10 ? "0" + secs : secs);
            }
        }
        
        // Initialize connection to backend
        window.addEventListener('load', connectToBackend);
        
        // Save position before page unloads
        window.addEventListener('beforeunload', function() {
            if (backend && currentTime > 0) {
                backend.savePosition();
            }
        });
    </script>
</body>
</html>
"""
        
        # Set the HTML content
        webview.setHtml(html_content)
        
        # Add navigation handler for playlist links
        webview.page().urlChanged.connect(lambda url: _handle_playlist_navigation(url, webview, document, db_session))
        
        logger.info(f"YouTube player set up for video ID: {video_id}")
        return True, callback
        
    except Exception as e:
        logger.exception(f"Error setting up YouTube player: {e}")
        webview.setHtml(f"<html><body><h2>Error loading YouTube player</h2><p>{str(e)}</p></body></html>")
        return False, None

def _handle_playlist_navigation(url, webview, document, db_session):
    """Handle navigation for playlist links.
    
    Args:
        url: QUrl that was navigated to
        webview: The QWebEngineView that's navigating
        document: The current document
        db_session: Database session
    """
    try:
        url_string = url.toString()
        
        # Check if this is a playlist navigation URL
        if url_string.startswith("playlist:"):
            # Parse the URL: playlist:playlist_id:position:direction
            parts = url_string.split(":")
            if len(parts) >= 4:
                playlist_id = int(parts[1])
                current_position = int(parts[2])
                direction = parts[3]  # "prev" or "next"
                
                # Get the playlist
                from core.knowledge_base.models import YouTubePlaylist, YouTubePlaylistVideo
                
                playlist = db_session.query(YouTubePlaylist).filter_by(id=playlist_id).first()
                if not playlist:
                    logger.error(f"Playlist not found: {playlist_id}")
                    return
                
                # Get the videos in this playlist
                videos = db_session.query(YouTubePlaylistVideo).filter_by(playlist_id=playlist_id).order_by(YouTubePlaylistVideo.position).all()
                if not videos:
                    logger.error(f"No videos found in playlist: {playlist_id}")
                    return
                
                # Find current video index
                current_index = None
                for i, video in enumerate(videos):
                    if video.position == current_position:
                        current_index = i
                        break
                
                if current_index is None:
                    logger.error(f"Current video position {current_position} not found in playlist {playlist_id}")
                    return
                
                # Get target video based on direction
                target_index = None
                if direction == "prev":
                    target_index = max(0, current_index - 1)
                elif direction == "next":
                    target_index = min(len(videos) - 1, current_index + 1)
                
                if target_index is None or target_index == current_index:
                    logger.warning(f"No {direction} video available from position {current_position}")
                    return
                
                # Get the target video
                target_video = videos[target_index]
                
                # Update the player
                from ui.document_view import DocumentView
                parent_widget = webview.parent()
                while parent_widget and not isinstance(parent_widget, DocumentView):
                    parent_widget = parent_widget.parent()
                
                if parent_widget and isinstance(parent_widget, DocumentView):
                    # Get target video document or create one if needed
                    if target_video.document_id:
                        # Load existing document
                        parent_widget.load_document(target_video.document_id)
                    else:
                        # We need to create a document for this video
                        # This should be handled by the DocumentView
                        # Just navigate to the video for now
                        logger.warning(f"Document not found for video {target_video.video_id}, opening in browser")
                        from PyQt6.QtGui import QDesktopServices
                        from PyQt6.QtCore import QUrl
                        QDesktopServices.openUrl(QUrl(f"https://www.youtube.com/watch?v={target_video.video_id}"))
                else:
                    logger.error("Could not find parent DocumentView to navigate to next video")
            
    except Exception as e:
        logger.exception(f"Error handling playlist navigation: {e}")

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
                        'origin': window.location.origin || 'https://www.youtube.com'
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