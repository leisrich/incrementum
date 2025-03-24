import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from PyQt6.QtCore import QTimer, QObject, pyqtSlot
from sqlalchemy import text

logger = logging.getLogger(__name__)

class DocumentPositionManager:
    """
    Manager class for handling document position tracking and restoration.
    """
    
    def __init__(self, document_view):
        """Initialize with document view reference."""
        self.document_view = document_view
        self.db_session = document_view.db_session
        self.current_document_id = None
        self.position_save_timer = None
        self.setup_autosave()
        
    def setup_autosave(self, interval=30000):
        """Set up automatic position saving (default: every 30 seconds)."""
        self.position_save_timer = QTimer()
        self.position_save_timer.timeout.connect(self.autosave_position)
        self.position_save_timer.start(interval)
        logger.debug(f"Set up autosave with interval of {interval}ms")
    
    def close_document(self):
        """Save position and cleanup when document is closed."""
        try:
            # Save final position
            if self.current_document_id:
                self.save_current_position()
                logger.debug(f"Saved final position for document {self.current_document_id}")
                
            # Reset current document
            self.current_document_id = None
        except Exception as e:
            logger.exception(f"Error in close_document: {e}")

        
    def autosave_position(self):
        """Automatically save current reading position."""
        if not self.current_document_id:
            return
            
        try:
            # Get current position based on document type
            self.save_current_position()
            logger.debug(f"Autosaved position for document {self.current_document_id}")
        except Exception as e:
            logger.exception(f"Error in autosave_position: {e}")
        
    def save_current_position(self):
        """Save current position for document."""
        if not self.current_document_id:
            return
            
        try:
            # Only proceed if document_view is still valid
            if not hasattr(self, 'document_view') or not self.document_view:
                logger.debug("Document view no longer exists, skipping position save")
                return
                
            # Check if content_edit is still valid
            if not hasattr(self.document_view, 'content_edit') or not self.document_view.content_edit:
                logger.debug("Content edit no longer exists, skipping position save")
                return
                
            content_edit = self.document_view.content_edit
            
            # Handle different widget types
            try:
                # For web view, get position using JavaScript
                if hasattr(content_edit, 'page') and callable(content_edit.page):
                    try:
                        script = "window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;"
                        content_edit.page().runJavaScript(
                            script,
                            lambda result: self._save_position_to_db(result)
                        )
                    except RuntimeError as e:
                        # Handle the case where the C++ object has been deleted
                        if "has been deleted" in str(e):
                            logger.warning(f"Widget has been deleted: {e}")
                        else:
                            raise
                    except Exception as e:
                        logger.debug(f"Error getting web position: {e}")
                elif hasattr(content_edit, 'verticalScrollBar'):
                    # For scrollable widgets
                    try:
                        scrollbar = content_edit.verticalScrollBar()
                        position = scrollbar.value()
                        self._save_position_to_db(position)
                    except RuntimeError as e:
                        # Handle the case where the C++ object has been deleted
                        if "has been deleted" in str(e):
                            logger.warning(f"Scrollbar widget has been deleted: {e}")
                        else:
                            raise
                elif hasattr(content_edit, 'get_view_state'):
                    # For PDF view
                    try:
                        view_state = content_edit.get_view_state()
                        position = view_state.get('page', 0)
                        self._save_position_to_db(position)
                    except RuntimeError as e:
                        # Handle the case where the C++ object has been deleted
                        if "has been deleted" in str(e):
                            logger.warning(f"PDF widget has been deleted: {e}")
                        else:
                            raise
                elif hasattr(content_edit, 'audioPosition'):
                    # For audio player
                    try:
                        position = content_edit.audioPosition()
                        self._save_position_to_db(position)
                    except RuntimeError as e:
                        # Handle the case where the C++ object has been deleted
                        if "has been deleted" in str(e):
                            logger.warning(f"Audio widget has been deleted: {e}")
                        else:
                            raise
                else:
                    logger.warning(f"Unsupported content edit type for position save")
            except RuntimeError as e:
                # Handle Qt C++ object deletion errors
                if "has been deleted" in str(e):
                    logger.warning(f"Widget has been deleted during position save: {e}")
                else:
                    raise
        except Exception as e:
            logger.exception(f"Error in save_current_position: {e}")
            
    def _save_position_to_db(self, position):
        """Save position to database."""
        try:
            if not self.current_document_id or position is None:
                return
                
            from core.knowledge_base.models import Document
            
            document = self.db_session.query(Document).get(self.current_document_id)
            if document:
                # Update document position
                document.position = position
                document.last_accessed = datetime.utcnow()
                self.db_session.commit()
                logger.debug(f"Saved position {position} for document {self.current_document_id}")
        except Exception as e:
            logger.exception(f"Error saving position to database: {e}")
    
    def restore_position(self, document_id):
        """Restore position for a document."""
        try:
            self.current_document_id = document_id
            
            # Get document info
            from core.knowledge_base.models import Document
            document = self.db_session.query(Document).get(document_id)
            
            if not document or document.position is None:
                logger.debug(f"No saved position for document {document_id}")
                return
                
            # Store position for later use
            position = document.position
            logger.debug(f"Retrieved saved position {position} for document {document_id}")
            
            # Restore based on document type and content widget
            content_edit = self.document_view.content_edit
            
            # Handle different widget types with appropriate delays
            if hasattr(content_edit, 'page') and callable(content_edit.page):
                # For web-based content (EPUB, HTML, YouTube)
                self._restore_web_position(content_edit, position)
            elif hasattr(content_edit, 'verticalScrollBar'):
                # For scrollable widgets
                self._restore_scrollbar_position(content_edit, position)
            elif hasattr(content_edit, 'setAudioPosition'):
                # For audio player
                content_edit.setAudioPosition(position)
                logger.debug(f"Restored audio position to {position}")
            elif hasattr(content_edit, 'goToPage'):
                # For PDF viewer
                content_edit.goToPage(position)
                logger.debug(f"Restored PDF page to {position}")
            
            logger.debug(f"Attempted to restore position {position} for document {document_id}")
            
        except Exception as e:
            logger.exception(f"Error restoring position: {e}")
    
    def _restore_web_position(self, web_view, position):
        """Restore position for web-based content with multiple attempts."""
        try:
            # Initial attempt
            self._apply_web_scroll(web_view, position)
            
            # Additional attempts with increasing delays
            for delay in [500, 1000, 2000, 3000]:
                QTimer.singleShot(delay, lambda: self._apply_web_scroll(web_view, position))
        except Exception as e:
            logger.exception(f"Error in _restore_web_position: {e}")
    
    def _apply_web_scroll(self, web_view, position):
        """Apply scroll position to web view."""
        try:
            # Simple scroll
            scroll_script = f"window.scrollTo(0, {position});"
            web_view.page().runJavaScript(scroll_script)
            logger.debug(f"Applied web scroll to position {position}")
            
            # Enhanced scroll for better reliability
            enhanced_script = f"""
            (function() {{
                // First attempt simple scroll
                window.scrollTo(0, {position});
                
                // Then force scroll on all potential elements
                var scrollElements = [
                    document.documentElement,
                    document.body,
                    document.querySelector('html'),
                    document.querySelector('body'),
                    document.querySelector('main'),
                    document.querySelector('.content'),
                    document.querySelector('#content'),
                    document.querySelector('.main')
                ];
                
                for (var i = 0; i < scrollElements.length; i++) {{
                    var el = scrollElements[i];
                    if (el) {{
                        el.scrollTop = {position};
                    }}
                }}
                
                // Also try to find and scroll any overflow elements
                var overflowElements = document.querySelectorAll('[style*="overflow"], [style*="overflow-y"]');
                for (var i = 0; i < overflowElements.length; i++) {{
                    var el = overflowElements[i];
                    var style = window.getComputedStyle(el);
                    if (style.overflow === 'auto' || style.overflow === 'scroll' || 
                        style.overflowY === 'auto' || style.overflowY === 'scroll') {{
                        el.scrollTop = {position};
                    }}
                }}
                
                // For EPUB content
                if (typeof window.epub !== 'undefined') {{
                    try {{
                        window.epub.goToPosition({position});
                    }} catch(e) {{
                        console.log('EPUB scroll error:', e);
                    }}
                }}
                
                return window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;
            }})();
            """
            web_view.page().runJavaScript(enhanced_script)
        except Exception as e:
            logger.debug(f"Error applying web scroll: {e}")
    
    def _restore_scrollbar_position(self, widget, position):
        """Restore scrollbar position for widgets with vertical scrollbars."""
        try:
            scrollbar = widget.verticalScrollBar()
            if scrollbar:
                scrollbar.setValue(position)
                logger.debug(f"Set scrollbar value to {position}")
                
                # Sometimes a single attempt isn't enough, try again after layout stabilizes
                QTimer.singleShot(500, lambda: scrollbar.setValue(position))
        except Exception as e:
            logger.debug(f"Error restoring scrollbar position: {e}")
    
    def cleanup(self):
        """Clean up resources."""
        try:
            # Stop the autosave timer
            if hasattr(self, 'position_save_timer') and self.position_save_timer:
                self.position_save_timer.stop()
                logger.debug("Stopped position autosave timer")
            
            # Save final position
            if self.current_document_id:
                try:
                    self.save_current_position()
                    logger.debug(f"Saved final position during cleanup for document {self.current_document_id}")
                except Exception as e:
                    logger.exception(f"Error saving final position during cleanup: {e}")
            
            # Clear references
            self.document_view = None
            self.db_session = None
            self.current_document_id = None
            
            logger.debug("Position manager cleanup completed")
        except Exception as e:
            logger.exception(f"Error in position manager cleanup: {e}")
