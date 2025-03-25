import os
import logging
import time
from typing import Optional, Dict, Any
from datetime import datetime
from PyQt6.QtCore import QTimer, QObject, pyqtSlot
from sqlalchemy import text

logger = logging.getLogger(__name__)

class DocumentPositionManager(QObject):
    """Manages document position tracking and restoration."""
    
    def __init__(self, document_view):
        """Initialize the position manager."""
        super().__init__()
        self.document_view = document_view
        self.db_session = document_view.db_session
        self.current_document_id = None
        
        # Create timer for periodic position saving
        self.timer = QTimer()
        self.timer.timeout.connect(self.save_position)
        self.timer.start(30000)  # Save position every 30 seconds
        
        # Track last save time to avoid too frequent saves
        self.last_save_time = 0
        
    def save_position(self) -> bool:
        """Save the current position to the document."""
        if not self.current_document_id:
            return False
            
        # Check if document view exists and has a document
        if not hasattr(self.document_view, 'document') or not self.document_view.document:
            logger.warning(f"Cannot save position: no document loaded")
            return False
            
        try:
            # Get current position based on content type
            position = self._get_current_position()
            if position is None:
                logger.warning(f"Couldn't determine position for document {self.current_document_id}")
                return False
                
            # Save to database
            self.document_view.document.position = position
            self.document_view.db_session.commit()
            
            # Update last save time
            self.last_save_time = time.time()
            
            logger.debug(f"Saved position {position} for document {self.current_document_id}")
            return True
            
        except Exception as e:
            logger.exception(f"Error saving document position: {e}")
            return False
            
    def _get_current_position(self) -> Optional[float]:
        """Get the current position in the document."""
        try:
            # For web view
            if hasattr(self.document_view, 'web_view') and self.document_view.web_view:
                # Execute JavaScript to get current scroll position
                def handle_scroll_result(result):
                    try:
                        if isinstance(result, (int, float)):
                            return float(result)
                        return None
                    except Exception:
                        return None
                        
                # Get position without waiting for callback
                # We'll rely on the periodic timer for actual saving
                self.document_view.web_view.page().runJavaScript(
                    "window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;",
                    handle_scroll_result
                )
                
                # Return last known position as fallback
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
            
    def cleanup(self):
        """Clean up resources."""
        try:
            if hasattr(self, 'timer') and self.timer.isActive():
                self.timer.stop()
                
            # Force a final position save
            self.save_position()
                
        except Exception as e:
            logger.exception(f"Error cleaning up position manager: {e}")
