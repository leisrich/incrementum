import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot
from sqlalchemy import text  # Import text for raw SQL queries

logger = logging.getLogger(__name__)

class PositionHistory:
    """Track position history for a document."""
    
    def __init__(self, max_entries=100):
        """Initialize with maximum number of history entries."""
        self.max_entries = max_entries
        self.positions = []  # List of (timestamp, position) tuples
    
    def add_position(self, position, timestamp=None):
        """Add a position to the history."""
        if timestamp is None:
            timestamp = datetime.utcnow()
            
        # Only add if position is different from last position
        if self.positions and abs(self.positions[-1][1] - position) < 10:
            # Just update timestamp of last entry
            self.positions[-1] = (timestamp, position)
            return
            
        # Add new position
        self.positions.append((timestamp, position))
        
        # Trim if needed
        if len(self.positions) > self.max_entries:
            self.positions = self.positions[-self.max_entries:]
    
    def get_last_position(self):
        """Get the last recorded position."""
        if not self.positions:
            return None
        return self.positions[-1][1]
    
    def get_position_at_time(self, target_time):
        """Get the position at a specific time."""
        if not self.positions:
            return None
            
        # Find the closest position before target_time
        for i in range(len(self.positions) - 1, -1, -1):
            if self.positions[i][0] <= target_time:
                return self.positions[i][1]
                
        # If all positions are after target_time, return the earliest
        return self.positions[0][1]
    
    def get_reading_speed(self, time_window=timedelta(minutes=10)):
        """Calculate reading speed over the specified time window."""
        if len(self.positions) < 2:
            return 0  # Not enough data
            
        # Get current time
        now = datetime.utcnow()
        
        # Find positions within time window
        window_start = now - time_window
        window_positions = [p for p in self.positions if p[0] >= window_start]
        
        if len(window_positions) < 2:
            return 0  # Not enough data in window
            
        # Calculate distance covered and time elapsed
        start_pos = window_positions[0][1]
        end_pos = window_positions[-1][1]
        distance = end_pos - start_pos
        
        start_time = window_positions[0][0]
        end_time = window_positions[-1][0]
        elapsed = (end_time - start_time).total_seconds()
        
        if elapsed <= 0:
            return 0
            
        # Return speed in position units per second
        return distance / elapsed
    
    def estimate_completion_time(self, total_length):
        """Estimate completion time based on current reading speed."""
        if len(self.positions) < 2:
            return None  # Not enough data
            
        # Get current position and speed
        current_pos = self.get_last_position()
        speed = self.get_reading_speed()
        
        if speed <= 0:
            return None  # Can't estimate with zero or negative speed
            
        # Calculate remaining distance
        remaining = total_length - current_pos
        
        if remaining <= 0:
            return None  # Already completed
            
        # Calculate remaining time in seconds
        remaining_seconds = remaining / speed
        
        # Return estimated completion time
        return datetime.utcnow() + timedelta(seconds=remaining_seconds)
    
    def to_dict(self):
        """Convert to dictionary for storage."""
        return {
            'max_entries': self.max_entries,
            'positions': [(p[0].isoformat(), p[1]) for p in self.positions]
        }
    
    @classmethod
    def from_dict(cls, data):
        """Create from dictionary data."""
        history = cls(max_entries=data.get('max_entries', 100))
        history.positions = [(datetime.fromisoformat(p[0]), p[1]) for p in data.get('positions', [])]
        return history


class DocumentPositionAutoSave(QObject):
    """Automatically saves document position at regular intervals."""
    
    # Signal emitted when position is saved
    positionSaved = pyqtSignal(int, float)  # document_id, position
    
    def __init__(self, document_view, interval=60000):
        """
        Initialize with document view reference.
        
        Args:
            document_view: Reference to the document view
            interval: Autosave interval in milliseconds (default: 60s)
        """
        super().__init__()
        self.document_view = document_view
        self.document_id = None
        self.last_save_time = 0
        self.interval = interval
        
        # Create timer for autosaving
        self.timer = QTimer()
        self.timer.timeout.connect(self.save_position)
        self.timer.start(interval)
        
        logger.debug(f"Position autosave initialized with interval {interval}ms")
        
    def set_document(self, document_id):
        """Set the current document ID."""
        if document_id != self.document_id:
            # Save position of previous document if any
            if self.document_id:
                self.save_position()
                
            # Set new document
            self.document_id = document_id
            self.last_save_time = 0  # Reset timer to force save for new document
            
    def save_position(self):
        """Save the current document position."""
        if not self.document_id:
            return
            
        # Check if document view exists and has a document
        if not hasattr(self.document_view, 'document') or not self.document_view.document:
            logger.warning(f"Cannot save position: no document loaded")
            return
            
        # Don't save too frequently
        current_time = time.time()
        if current_time - self.last_save_time < 5:  # At least 5 seconds between saves
            return
            
        try:
            # Get current position based on content type
            position = self._get_current_position()
            if position is None:
                return
                
            # Save to database
            self.document_view.document.position = position
            self.document_view.db_session.commit()
            
            # Update last save time
            self.last_save_time = current_time
            
            # Emit signal
            self.positionSaved.emit(self.document_id, position)
            
            logger.debug(f"Autosaved position {position} for document {self.document_id}")
            
        except Exception as e:
            logger.exception(f"Error autosaving position: {e}")
            
    def _get_current_position(self) -> Optional[float]:
        """Get the current position in the document."""
        try:
            # For web view
            if hasattr(self.document_view, 'web_view') and self.document_view.web_view:
                # This is asynchronous, so we use the last known position
                # The real position will be saved on the next timer tick
                return float(getattr(self.document_view.document, 'position', 0))
                
            # For text edit or other scrollable widgets
            elif hasattr(self.document_view, 'content_edit') and hasattr(self.document_view.content_edit, 'verticalScrollBar'):
                scrollbar = self.document_view.content_edit.verticalScrollBar()
                if scrollbar:
                    return float(scrollbar.value())
                    
            # For PDF view
            elif hasattr(self.document_view, 'pdf_view') and hasattr(self.document_view.pdf_view, 'currentPage'):
                return float(self.document_view.pdf_view.currentPage())
                
            # For audio player
            elif hasattr(self.document_view, 'audio_player') and hasattr(self.document_view.audio_player, 'audioPosition'):
                return float(self.document_view.audio_player.audioPosition())
                
            # Fallback to existing position
            if hasattr(self.document_view.document, 'position'):
                return float(self.document_view.document.position)
                
            return 0.0
            
        except Exception as e:
            logger.exception(f"Error getting current position: {e}")
            return None
            
    def stop(self):
        """Stop the autosave timer."""
        if hasattr(self, 'timer') and self.timer.isActive():
            self.timer.stop()
            
        # Save position one final time
        self.save_position()
