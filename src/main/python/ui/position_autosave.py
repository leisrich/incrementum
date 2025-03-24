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
    """Auto-save document position at regular intervals."""
    
    positionSaved = pyqtSignal(int, float)  # document_id, position
    readingStatsUpdated = pyqtSignal(dict)  # stats dictionary
    
    def __init__(self, document_view, interval=30000):
        """Initialize with document view and save interval in milliseconds."""
        super().__init__()
        self.document_view = document_view
        self.db_session = document_view.db_session
        self.interval = interval
        self.current_document_id = None
        self.timer = None
        self.history = {}  # Dictionary of document_id -> PositionHistory
        self.load_history()
        self.setup_timer()
    
    def setup_timer(self):
        """Set up the auto-save timer."""
        self.timer = QTimer()
        self.timer.timeout.connect(self.save_position)
        self.timer.start(self.interval)
        logger.debug(f"Position auto-save timer started with interval {self.interval}ms")
    
    def set_document(self, document_id):
        """Set the current document."""
        self.current_document_id = document_id
        
        # Initialize history for this document if needed
        if document_id not in self.history:
            self.history[document_id] = PositionHistory()
            
        # Initial save
        self.save_position()
        
        # Update document info
        self.update_document_info()
    
    def save_position(self):
        """Save current position."""
        if not self.current_document_id:
            return
        
        try:
            # Get current position
            position = self.get_current_position()
            
            if position is None:
                return
                
            # Update position history
            if self.current_document_id in self.history:
                self.history[self.current_document_id].add_position(position)
            
            # Save to database
            try:
                from core.knowledge_base.models import Document
                
                document = self.db_session.query(Document).get(self.current_document_id)
                if document:
                    document.position = position
                    document.last_accessed = datetime.utcnow()
                    self.db_session.commit()
                    
                    # Emit signal
                    self.positionSaved.emit(self.current_document_id, position)
                    
                    # Save history
                    self.save_history()
                    
                    # Update reading stats
                    self.update_reading_stats()
                    
                    logger.debug(f"Auto-saved position {position} for document {self.current_document_id}")
            except Exception as e:
                logger.exception(f"Error auto-saving position: {e}")
        except Exception as e:
            logger.exception(f"Error in save_position: {e}")
    
    def get_current_position(self):
        """Get current position from document view."""
        try:
            # Check if document_view is still valid
            if not hasattr(self, 'document_view') or self.document_view is None:
                logger.warning("Document view is no longer valid")
                return None
                
            # Check if content_edit exists
            if not hasattr(self.document_view, 'content_edit') or self.document_view.content_edit is None:
                logger.warning("Content edit widget not available")
                return None
                
            content_edit = self.document_view.content_edit
            
            # Handle different widget types
            try:
                if hasattr(content_edit, 'page') and callable(content_edit.page):
                    # For web view, get position using JavaScript
                    return self._get_webview_position()
                    
                elif hasattr(content_edit, 'verticalScrollBar'):
                    # For scrollable widgets
                    try:
                        scrollbar = content_edit.verticalScrollBar()
                        return scrollbar.value()
                    except RuntimeError as e:
                        if "has been deleted" in str(e):
                            logger.warning(f"Scrollbar widget has been deleted: {e}")
                            return None
                        raise
                    
                elif hasattr(content_edit, 'get_view_state'):
                    # For PDF viewer
                    try:
                        view_state = content_edit.get_view_state()
                        return view_state.get('page', 0)
                    except RuntimeError as e:
                        if "has been deleted" in str(e):
                            logger.warning(f"PDF widget has been deleted: {e}")
                            return None
                        raise
                    
                elif hasattr(content_edit, 'audioPosition'):
                    # For audio player
                    try:
                        return content_edit.audioPosition()
                    except RuntimeError as e:
                        if "has been deleted" in str(e):
                            logger.warning(f"Audio widget has been deleted: {e}")
                            return None
                        raise
                        
                elif hasattr(content_edit, 'currentPage'):
                    # For PDF viewer (older interface)
                    try:
                        return content_edit.currentPage()
                    except RuntimeError as e:
                        if "has been deleted" in str(e):
                            logger.warning(f"PDF widget has been deleted: {e}")
                            return None
                        raise
                        
                else:
                    logger.warning(f"Unable to determine position for content type")
                    return None
            except RuntimeError as e:
                if "has been deleted" in str(e):
                    logger.warning(f"Widget has been deleted during position check: {e}")
                    return None
                raise
                
        except Exception as e:
            logger.exception(f"Error getting current position: {e}")
            return None
    
    def _get_webview_position(self):
        """Get position from web view using JavaScript."""
        # This requires using a callback since JavaScript execution is asynchronous
        # We'll use a simple blocking approach with a timeout
        try:
            result = [None]
            done = [False]
            
            def callback(value):
                result[0] = value
                done[0] = True
            
            # Check if content_edit exists and is valid
            if not hasattr(self.document_view, 'content_edit') or self.document_view.content_edit is None:
                logger.warning("No content_edit available for position tracking")
                return None
                
            # Use web_view if available as it's more specifically for web content
            web_view = getattr(self.document_view, 'web_view', None)
            view_to_use = web_view if web_view is not None else self.document_view.content_edit
            
            try:
                # Request scroll position
                script = "window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;"
                view_to_use.page().runJavaScript(script, callback)
                
                # Wait for result with timeout
                start_time = time.time()
                while not done[0] and time.time() - start_time < 1.0:
                    from PyQt6.QtCore import QCoreApplication
                    QCoreApplication.processEvents()
                    time.sleep(0.01)
                
                return result[0]
            except RuntimeError as e:
                # Handle the case where the object has been deleted
                logger.warning(f"QWebEngineView is no longer valid: {e}")
                return None
                
        except Exception as e:
            logger.exception(f"Error getting webview position: {e}")
            return None
    
    def load_history(self):
        """Load position history from database."""
        try:
            # Check if position_history table exists
            result = self.db_session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='position_history'")
            )
            
            if not result.fetchone():
                # Create table
                self.db_session.execute(text("""
                CREATE TABLE position_history (
                    id INTEGER PRIMARY KEY,
                    document_id INTEGER NOT NULL,
                    data TEXT NOT NULL
                )
                """))
                self.db_session.commit()
                logger.info("Created position_history table")
                return
            
            # Load history data
            import json
            result = self.db_session.execute(
                text("SELECT document_id, data FROM position_history")
            )
            
            for row in result:
                try:
                    document_id = row[0]
                    data = json.loads(row[1])
                    self.history[document_id] = PositionHistory.from_dict(data)
                except Exception as e:
                    logger.error(f"Error loading position history for document {row[0]}: {e}")
            
            logger.info(f"Loaded position history for {len(self.history)} documents")
                
        except Exception as e:
            logger.exception(f"Error loading position history: {e}")
    
    def save_history(self):
        """Save position history to database."""
        try:
            import json
            
            # Save each document's history
            for document_id, history in self.history.items():
                data = json.dumps(history.to_dict())
                
                # Check if entry exists
                result = self.db_session.execute(
                    text("SELECT id FROM position_history WHERE document_id = :doc_id"),
                    {"doc_id": document_id}
                )
                
                if result.fetchone():
                    # Update existing
                    self.db_session.execute(
                        text("UPDATE position_history SET data = :data WHERE document_id = :doc_id"),
                        {"data": data, "doc_id": document_id}
                    )
                else:
                    # Insert new
                    self.db_session.execute(
                        text("INSERT INTO position_history (document_id, data) VALUES (:doc_id, :data)"),
                        {"doc_id": document_id, "data": data}
                    )
            
            self.db_session.commit()
            logger.debug(f"Saved position history for {len(self.history)} documents")
                
        except Exception as e:
            logger.exception(f"Error saving position history: {e}")
    
    def update_reading_stats(self):
        """Update reading statistics and emit signal."""
        if not self.current_document_id or self.current_document_id not in self.history:
            return
            
        try:
            from core.knowledge_base.models import Document
            
            document = self.db_session.query(Document).get(self.current_document_id)
            if not document:
                return
                
            # Get history
            history = self.history[self.current_document_id]
            
            # Calculate stats
            stats = {
                'document_id': self.current_document_id,
                'document_title': document.title,
                'current_position': history.get_last_position(),
                'reading_speed': history.get_reading_speed(),
            }
            
            # Get document length for progress calculation
            doc_length = self._get_document_length()
            if doc_length:
                stats['document_length'] = doc_length
                stats['progress_percent'] = min(100.0, (stats['current_position'] / doc_length) * 100)
                
                # Estimate completion time
                completion_time = history.estimate_completion_time(doc_length)
                if completion_time:
                    stats['estimated_completion'] = completion_time.isoformat()
            
            # Add reading session info
            stats['current_session_duration'] = self._get_current_session_duration()
            stats['total_reading_time'] = self._get_total_reading_time()
            
            # Emit signal with stats
            self.readingStatsUpdated.emit(stats)
                
        except Exception as e:
            logger.exception(f"Error updating reading stats: {e}")
    
    def _get_document_length(self):
        """Get total document length in position units."""
        try:
            content_edit = self.document_view.content_edit
            
            # Handle different widget types
            if hasattr(content_edit, 'page') and callable(content_edit.page):
                # For web view, get document height using JavaScript
                result = [None]
                done = [False]
                
                def callback(value):
                    result[0] = value
                    done[0] = True
                
                script = """
                Math.max(
                    document.body.scrollHeight,
                    document.documentElement.scrollHeight,
                    document.body.offsetHeight,
                    document.documentElement.offsetHeight
                ) - window.innerHeight;
                """
                content_edit.page().runJavaScript(script, callback)
                
                # Wait for result with timeout
                start_time = time.time()
                while not done[0] and time.time() - start_time < 1.0:
                    from PyQt6.QtCore import QCoreApplication
                    QCoreApplication.processEvents()
                    time.sleep(0.01)
                
                return result[0]
                
            elif hasattr(content_edit, 'verticalScrollBar'):
                # For scrollable widgets
                scrollbar = content_edit.verticalScrollBar()
                return scrollbar.maximum()
                
            elif hasattr(content_edit, 'duration'):
                # For audio player
                return content_edit.duration()
                
            elif hasattr(content_edit, 'pageCount'):
                # For PDF viewer
                return content_edit.pageCount()
                
            return None
                
        except Exception as e:
            logger.exception(f"Error getting document length: {e}")
            return None
    
    def _get_current_session_duration(self):
        """Get duration of current reading session in seconds."""
        try:
            # Get document info
            from core.knowledge_base.models import Document
            
            document = self.db_session.query(Document).get(self.current_document_id)
            if not document or not document.last_accessed:
                return 0
                
            # Get session start time
            session_start = document.last_accessed
            
            # Calculate duration
            duration = (datetime.utcnow() - session_start).total_seconds()
            
            # If more than 30 minutes gap in history, consider it a new session
            if self.current_document_id in self.history and self.history[self.current_document_id].positions:
                history = self.history[self.current_document_id]
                timestamps = [pos[0] for pos in history.positions]
                timestamps.sort()
                
                # Find the most recent gap > 30 minutes
                for i in range(len(timestamps) - 1, 0, -1):
                    gap = (timestamps[i] - timestamps[i-1]).total_seconds()
                    if gap > 1800:  # 30 minutes
                        session_start = timestamps[i]
                        break
                
                duration = (datetime.utcnow() - session_start).total_seconds()
            
            return duration
                
        except Exception as e:
            logger.exception(f"Error calculating session duration: {e}")
            return 0
    
    def _get_total_reading_time(self):
        """Get total reading time for document in seconds."""
        try:
            if self.current_document_id not in self.history:
                return 0
                
            history = self.history[self.current_document_id]
            
            # Calculate total time while accounting for gaps
            total_time = 0
            session_start = None
            last_timestamp = None
            
            for timestamp, _ in sorted(history.positions):
                if session_start is None:
                    # Start first session
                    session_start = timestamp
                    last_timestamp = timestamp
                    continue
                
                # Calculate gap
                gap = (timestamp - last_timestamp).total_seconds()
                
                if gap > 1800:  # 30 minutes gap = new session
                    # Add previous session time
                    total_time += (last_timestamp - session_start).total_seconds()
                    
                    # Start new session
                    session_start = timestamp
                
                last_timestamp = timestamp
            
            # Add final session time
            if session_start and last_timestamp:
                total_time += (last_timestamp - session_start).total_seconds()
            
            return total_time
                
        except Exception as e:
            logger.exception(f"Error calculating total reading time: {e}")
            return 0
    
    def update_document_info(self):
        """Update document info with reading statistics."""
        if not self.current_document_id:
            return
            
        try:
            from core.knowledge_base.models import Document
            import json
            
            document = self.db_session.query(Document).get(self.current_document_id)
            if not document:
                return
                
            # Get extra info dictionary or create one
            extra_info = {}
            if hasattr(document, 'extra_info') and document.extra_info:
                try:
                    extra_info = json.loads(document.extra_info)
                except:
                    extra_info = {}
            
            # Update reading statistics
            if 'reading_stats' not in extra_info:
                extra_info['reading_stats'] = {}
                
            reading_stats = extra_info['reading_stats']
            
            # Update total reading time
            reading_stats['total_time'] = self._get_total_reading_time()
            
            # Update reading sessions
            if 'sessions' not in reading_stats:
                reading_stats['sessions'] = []
                
            # Check if we should add a new session
            last_session_end = None
            if reading_stats['sessions']:
                last_session = reading_stats['sessions'][-1]
                if 'end_time' in last_session:
                    last_session_end = datetime.fromisoformat(last_session['end_time'])
            
            current_time = datetime.utcnow()
            
            # If no sessions or last session was more than 30 minutes ago, create a new one
            if not reading_stats['sessions'] or (last_session_end and (current_time - last_session_end).total_seconds() > 1800):
                # Add new session
                reading_stats['sessions'].append({
                    'start_time': current_time.isoformat(),
                    'end_time': current_time.isoformat(),
                    'start_position': self.get_current_position() or 0
                })
            else:
                # Update current session
                reading_stats['sessions'][-1]['end_time'] = current_time.isoformat()
                reading_stats['sessions'][-1]['end_position'] = self.get_current_position() or 0
                
                # Calculate session duration
                start_time = datetime.fromisoformat(reading_stats['sessions'][-1]['start_time'])
                reading_stats['sessions'][-1]['duration'] = (current_time - start_time).total_seconds()
            
            # Limit number of sessions to keep
            if len(reading_stats['sessions']) > 50:
                reading_stats['sessions'] = reading_stats['sessions'][-50:]
            
            # Save updated extra info
            document.extra_info = json.dumps(extra_info)
            self.db_session.commit()
                
        except Exception as e:
            logger.exception(f"Error updating document info: {e}")
