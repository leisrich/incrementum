# ui/load_audio_helper.py
#
# This module provides audio playback with position tracking for Incrementum.

import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime

from PyQt6.QtCore import Qt, QUrl, QTimer, QObject, pyqtSlot, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QSlider, QStyle, 
    QSpinBox, QDoubleSpinBox, QComboBox,
    QFrame
)
from PyQt6.QtMultimedia import (
    QMediaPlayer, QAudioOutput, 
    QMediaMetaData, QMediaFormat
)
from PyQt6.QtGui import QPainter, QBrush, QPen, QColor

logger = logging.getLogger(__name__)

class AudioVisualizer(QWidget):
    """Audio visualizer that shows a visual representation of audio playback."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(60)
        self.setMaximumHeight(100)
        self.bars = 20  # Number of bars in the visualizer
        self.bar_values = [0] * self.bars
        self.bar_colors = []
        self.is_active = False
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.update_bars)
        self.animation_timer.setInterval(50)  # 50ms update rate (20fps)
        self.setStyleSheet("background-color: #222;")
        
        # Generate gradient colors from blue to red
        for i in range(self.bars):
            # Generate colors from blue to cyan to green to yellow to red
            if i < self.bars / 5:
                # Blue to cyan
                r = 0
                g = int(255 * (i / (self.bars / 5)))
                b = 255
            elif i < 2 * self.bars / 5:
                # Cyan to green
                r = 0
                g = 255
                b = int(255 * (1 - (i - self.bars / 5) / (self.bars / 5)))
            elif i < 3 * self.bars / 5:
                # Green to yellow
                r = int(255 * ((i - 2 * self.bars / 5) / (self.bars / 5)))
                g = 255
                b = 0
            elif i < 4 * self.bars / 5:
                # Yellow to orange
                r = 255
                g = int(255 * (1 - (i - 3 * self.bars / 5) / (self.bars / 5)))
                b = 0
            else:
                # Orange to red
                r = 255
                g = int(128 * (1 - (i - 4 * self.bars / 5) / (self.bars / 5)))
                b = 0
                
            self.bar_colors.append(QColor(r, g, b))
    
    def start(self):
        """Start the visualizer animation."""
        self.is_active = True
        self.animation_timer.start()
        
    def stop(self):
        """Stop the visualizer animation."""
        self.is_active = False
        self.animation_timer.stop()
        # Reset bars to zero
        self.bar_values = [0] * self.bars
        self.update()
        
    def update_bars(self):
        """Update the bar values for animation."""
        if not self.is_active:
            return
            
        import random
        # Generate new random values for each bar
        for i in range(self.bars):
            # Custom algorithm to make the bars look more like an audio visualizer
            # Center bars tend to be higher, edges lower
            center_weight = 1.0 - 0.6 * abs(i - self.bars / 2) / (self.bars / 2)
            max_height = 0.3 + 0.7 * center_weight
            
            # Random movement with some persistence of previous value
            target = random.random() * max_height
            # Smooth transition - 70% new value, 30% old value
            self.bar_values[i] = 0.3 * self.bar_values[i] + 0.7 * target
        
        # Request a repaint
        self.update()
        
    def paintEvent(self, event):
        """Paint the visualizer bars."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Get widget dimensions
        width = self.width()
        height = self.height()
        
        # Calculate bar width and spacing
        bar_width = width / (self.bars * 1.5)  # Bar width with spacing
        spacing = bar_width / 2  # Spacing between bars
        
        # Draw each bar
        for i in range(self.bars):
            # Calculate bar height and position
            bar_height = self.bar_values[i] * height
            x = i * (bar_width + spacing) + spacing
            y = height - bar_height
            
            # Set brush and pen
            painter.setBrush(QBrush(self.bar_colors[i]))
            painter.setPen(QPen(Qt.GlobalColor.transparent))
            
            # Draw rounded rectangle for each bar
            painter.drawRoundedRect(
                int(x), 
                int(y), 
                int(bar_width), 
                int(bar_height), 
                2.0, 
                2.0
            )

class AudioPlayerWidget(QWidget):
    """Custom audio player widget with playback controls and position tracking."""
    
    positionSaved = pyqtSignal()  # Signal emitted when position is saved
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.document = None
        self.db_session = None
        self.current_position = 0
        self.audio_duration = 0
        self.last_save_position = 0
        self.player_state = None
        self.playback_rate = 1.0
        
        # Check if QtMultimedia is available
        self.QT_MULTIMEDIA_AVAILABLE = False
        try:
            from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
            self.QT_MULTIMEDIA_AVAILABLE = True
        except ImportError:
            logger.error("QtMultimedia is not available - audio player will be limited")
            # Create a UI with limited functionality
            self._create_limited_ui()
            return
            
        try:
            # Create media player
            self.player = QMediaPlayer()
            self.audio_output = QAudioOutput()
            self.player.setAudioOutput(self.audio_output)
            
            # Store enums for state tracking
            self.player_state = QMediaPlayer.PlaybackState.StoppedState
            
            # Connect signals
            self.player.positionChanged.connect(self.on_position_changed)
            self.player.durationChanged.connect(self.on_duration_changed)
            self.player.playbackStateChanged.connect(self.on_state_changed)
            self.player.errorOccurred.connect(self.on_error)
            
            # Set up the UI
            self.init_ui()
            
            # Auto-save timer
            self.auto_save_timer = QTimer(self)
            self.auto_save_timer.setInterval(5000)  # 5 seconds
            self.auto_save_timer.timeout.connect(self.auto_save_position)
            self.auto_save_timer.start()
            
        except Exception as e:
            logger.exception(f"Error initializing audio player: {e}")
            # Create a limited UI if initialization fails
            self._create_limited_ui()
    
    def _create_limited_ui(self):
        """Create a limited UI when QtMultimedia is not available."""
        main_layout = QVBoxLayout(self)
        
        # Error message
        error_label = QLabel("Audio playback is not available due to missing or incompatible QtMultimedia module.")
        error_label.setStyleSheet("color: red; font-weight: bold;")
        error_label.setWordWrap(True)
        main_layout.addWidget(error_label)
        
        # Document info
        self.title_label = QLabel("No audio loaded")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        main_layout.addWidget(self.title_label)
        
        self.author_label = QLabel("")
        self.author_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.author_label)
        
        # Open with system player button
        self.open_system_button = QPushButton("Open with System Player")
        self.open_system_button.clicked.connect(self._open_with_system_player)
        main_layout.addWidget(self.open_system_button)
        
        # Add spacer
        main_layout.addStretch(1)
        
        # Add suggestions for fixing
        fix_label = QLabel("Suggested fix: Try updating PyQt6-Multimedia with: pip install PyQt6-Multimedia==6.6.1 -U")
        fix_label.setStyleSheet("color: #333; font-style: italic;")
        fix_label.setWordWrap(True)
        main_layout.addWidget(fix_label)
    
    def _open_with_system_player(self):
        """Open the audio file with the system's default player."""
        try:
            if not hasattr(self, 'document') or not hasattr(self.document, 'file_path'):
                return
                
            from PyQt6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.document.file_path))
            
        except Exception as e:
            logger.exception(f"Error opening file with system player: {e}")
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", f"Could not open the file with system player: {str(e)}")
    
    def init_ui(self):
        """Initialize the user interface."""
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Info panel
        info_panel = QFrame()
        info_panel.setFrameShape(QFrame.Shape.StyledPanel)
        info_panel.setFrameShadow(QFrame.Shadow.Raised)
        info_layout = QVBoxLayout(info_panel)
        
        # Title
        self.title_label = QLabel("No audio loaded")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        info_layout.addWidget(self.title_label)
        
        # Author
        self.author_label = QLabel("")
        self.author_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_layout.addWidget(self.author_label)
        
        # Add info panel to main layout
        main_layout.addWidget(info_panel)
        
        # Add the visualizer
        self.visualizer = AudioVisualizer(self)
        self.visualizer.setMinimumHeight(80)
        main_layout.addWidget(self.visualizer)
        
        # Controls panel
        controls_panel = QFrame()
        controls_layout = QVBoxLayout(controls_panel)
        
        # Time display
        time_layout = QHBoxLayout()
        self.position_label = QLabel("0:00")
        self.duration_label = QLabel("0:00")
        time_layout.addWidget(self.position_label)
        time_layout.addStretch()
        time_layout.addWidget(self.duration_label)
        controls_layout.addLayout(time_layout)
        
        # Seek slider
        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.sliderMoved.connect(self.seek_position)
        self.seek_slider.sliderPressed.connect(self.on_slider_pressed)
        self.seek_slider.sliderReleased.connect(self.on_slider_released)
        controls_layout.addWidget(self.seek_slider)
        
        # Playback controls
        playback_layout = QHBoxLayout()
        
        # Rewind button (back 15 seconds)
        self.rewind_button = QPushButton()
        self.rewind_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaSeekBackward))
        self.rewind_button.setToolTip("Rewind 15 seconds")
        self.rewind_button.clicked.connect(self.rewind)
        playback_layout.addWidget(self.rewind_button)
        
        # Play/Pause button
        self.play_button = QPushButton()
        self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.play_button.clicked.connect(self.toggle_play)
        playback_layout.addWidget(self.play_button)
        
        # Forward button (forward 15 seconds)
        self.forward_button = QPushButton()
        self.forward_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaSeekForward))
        self.forward_button.setToolTip("Forward 15 seconds")
        self.forward_button.clicked.connect(self.forward)
        playback_layout.addWidget(self.forward_button)
        
        # Playback rate control
        playback_layout.addStretch()
        playback_layout.addWidget(QLabel("Speed:"))
        self.rate_combo = QComboBox()
        self.rate_combo.addItems(["0.75x", "1.0x", "1.25x", "1.5x", "1.75x", "2.0x"])
        self.rate_combo.setCurrentIndex(1)  # 1.0x by default
        self.rate_combo.currentIndexChanged.connect(self.change_playback_rate)
        playback_layout.addWidget(self.rate_combo)
        
        controls_layout.addLayout(playback_layout)
        
        # Manual position control
        position_layout = QHBoxLayout()
        position_layout.addWidget(QLabel("Position:"))
        self.position_spinbox = QDoubleSpinBox()
        self.position_spinbox.setRange(0, 0)
        self.position_spinbox.setDecimals(1)
        self.position_spinbox.setSingleStep(1.0)
        self.position_spinbox.setSuffix(" sec")
        self.position_spinbox.editingFinished.connect(self.jump_to_position)
        position_layout.addWidget(self.position_spinbox)
        
        self.save_button = QPushButton("Save Position")
        self.save_button.clicked.connect(self.save_position)
        position_layout.addWidget(self.save_button)
        
        controls_layout.addLayout(position_layout)
        
        # Status
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #666; font-style: italic;")
        controls_layout.addWidget(self.status_label)
        
        # Add controls panel to main layout
        main_layout.addWidget(controls_panel)
        
    def setup(self, document, db_session, target_position=0):
        """Set up the audio player with a document and database session.
        
        Args:
            document: The document to play
            db_session: Database session for saving positions
            target_position: Initial position in seconds
        """
        self.document = document
        self.db_session = db_session
        
        # Get the initial position, either from argument or from document
        if hasattr(document, 'position') and document.position is not None:
            self.current_position = document.position
            self.last_save_position = document.position
        else:
            self.current_position = target_position
            self.last_save_position = target_position
        
        # Check if QtMultimedia is available and player was created
        if not hasattr(self, 'player'):
            # Update UI with document info for limited player
            self.title_label.setText(document.title)
            self.author_label.setText(document.author if document.author else "")
            return
            
        # Set the media source
        self.player.setSource(QUrl.fromLocalFile(document.file_path))
        
        # Set initial volume
        self.audio_output.setVolume(0.8)  # 80% volume
        
        # Update UI with document info
        self.title_label.setText(document.title)
        self.author_label.setText(document.author if document.author else "")
        self.status_label.setText("Loading audio...")
        
        # Set initial position after a short delay to allow media to load
        QTimer.singleShot(500, lambda: self.set_initial_position(self.current_position))
    
    def set_initial_position(self, position):
        """Set the initial position after the media has loaded."""
        if position > 0:
            self.player.setPosition(int(position * 1000))  # Convert to milliseconds
            self.position_spinbox.setValue(position)
    
    def toggle_play(self):
        """Toggle play/pause state."""
        if self.player_state == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.visualizer.stop()
        else:
            self.player.play()
            self.visualizer.start()
    
    def seek_position(self, position):
        """Seek to a position in the audio.
        
        Args:
            position: Position in the slider's value (milliseconds)
        """
        self.player.setPosition(position)
    
    def rewind(self):
        """Rewind 15 seconds."""
        current_pos = self.player.position()
        new_pos = max(0, current_pos - 15000)  # 15 seconds in ms
        self.player.setPosition(new_pos)
    
    def forward(self):
        """Fast forward 15 seconds."""
        current_pos = self.player.position()
        new_pos = min(self.player.duration(), current_pos + 15000)  # 15 seconds in ms
        self.player.setPosition(new_pos)
    
    def jump_to_position(self):
        """Jump to the position specified in the spinbox."""
        seconds = self.position_spinbox.value()
        self.player.setPosition(int(seconds * 1000))  # Convert to milliseconds
    
    def change_playback_rate(self, index):
        """Change the playback rate.
        
        Args:
            index: Index of the selected rate in the combo box
        """
        rate_text = self.rate_combo.currentText()
        rate = float(rate_text.replace('x', ''))
        self.playback_rate = rate
        self.player.setPlaybackRate(rate)
    
    def on_position_changed(self, position):
        """Handle position change in the player.
        
        Args:
            position: Current position in milliseconds
        """
        # Update the slider
        self.seek_slider.setValue(position)
        
        # Update position label with formatted time
        seconds = position / 1000
        self.current_position = seconds
        self.position_label.setText(self.format_time(seconds))
        
        # Update position spinbox if not being edited
        if not self.position_spinbox.hasFocus():
            self.position_spinbox.setValue(seconds)
    
    def on_duration_changed(self, duration):
        """Handle duration change in the player.
        
        Args:
            duration: Duration in milliseconds
        """
        self.audio_duration = duration / 1000
        self.seek_slider.setRange(0, duration)
        self.position_spinbox.setRange(0, self.audio_duration)
        self.duration_label.setText(self.format_time(self.audio_duration))
        self.status_label.setText(f"Audio loaded: {self.format_time(self.audio_duration)}")
    
    def on_state_changed(self, state):
        """Handle changes in playback state."""
        self.player_state = state
        
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
            self.status_label.setText("Playing")
            # Start visualizer animation
            self.visualizer.start()
        else:
            self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
            if state == QMediaPlayer.PlaybackState.PausedState:
                self.status_label.setText("Paused")
            else:
                self.status_label.setText("Stopped")
            # Stop visualizer animation when not playing
            self.visualizer.stop()
            
        # Update UI
        self.update()
    
    def on_error(self, error, errorString):
        """Handle player errors.
        
        Args:
            error: Error code
            errorString: Error message
        """
        logger.error(f"Audio player error: {error} - {errorString}")
        self.status_label.setText(f"Error: {errorString}")
    
    def on_slider_pressed(self):
        """Handle slider press event."""
        # Pause updates from the player while the user is adjusting the slider
        self.player.positionChanged.disconnect(self.on_position_changed)
    
    def on_slider_released(self):
        """Handle slider release event."""
        # Seek to the position the user dragged to
        self.player.setPosition(self.seek_slider.value())
        # Reconnect position updates
        self.player.positionChanged.connect(self.on_position_changed)
    
    def save_position(self):
        """Save the current position to the document."""
        try:
            if self.document and self.db_session:
                seconds = self.current_position
                
                # Update document's position
                self.document.position = seconds
                self.document.last_modified = datetime.now()
                self.document.last_accessed = datetime.now()
                
                # Save to database
                self.db_session.commit()
                
                # Update last saved position
                self.last_save_position = seconds
                
                self.status_label.setText(f"Position saved: {self.format_time(seconds)}")
                self.positionSaved.emit()
                return True
            
            return False
        except Exception as e:
            logger.error(f"Error saving position: {e}")
            self.status_label.setText(f"Error saving position: {str(e)}")
            return False
    
    def auto_save_position(self):
        """Auto-save position if needed."""
        try:
            # Only save if position has changed significantly (30+ seconds)
            if abs(self.current_position - self.last_save_position) >= 30:
                if self.save_position():
                    logger.debug(f"Auto-saved position: {self.format_time(self.current_position)}")
        except Exception as e:
            logger.error(f"Error in auto-save: {e}")
    
    @staticmethod
    def format_time(seconds):
        """Format seconds as minutes:seconds.
        
        Args:
            seconds: Time in seconds
            
        Returns:
            Formatted time string (e.g., "5:23")
        """
        minutes = int(seconds) // 60
        secs = int(seconds) % 60
        return f"{minutes}:{secs:02d}"
    
    def closeEvent(self, event):
        """Handle the close event."""
        try:
            # Stop playback
            if self.player:
                self.player.stop()
            
            # Save the current position
            self.save_position()
            
            # Stop visualizer and timers
            self.visualizer.stop()
            if self.auto_save_timer.isActive():
                self.auto_save_timer.stop()
                
        except Exception as e:
            logger.error(f"Error in AudioPlayerWidget.closeEvent: {e}")
            
        # Accept the event
        event.accept()

def setup_audio_player(parent, document, db_session, target_position=0):
    """Set up an audio player for the document.
    
    Args:
        parent: Parent widget
        document: The document to play
        db_session: Database session for saving positions
        target_position: Starting position in seconds
    
    Returns:
        AudioPlayerWidget: The configured audio player widget
    """
    try:
        # Check if QtMultimedia is available
        QT_MULTIMEDIA_AVAILABLE = True
        try:
            from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
        except ImportError:
            QT_MULTIMEDIA_AVAILABLE = False
            logger.warning("PyQt6-Multimedia is not available - audio playback will be limited")

        # Create audio player widget
        player = AudioPlayerWidget(parent)
        
        # Set up with document
        player.setup(document, db_session, target_position)
        
        return player
    except Exception as e:
        logger.exception(f"Failed to set up audio player: {e}")
        error_label = QLabel(f"Error loading audio player: {str(e)}")
        error_label.setStyleSheet("color: red;")
        return error_label 
