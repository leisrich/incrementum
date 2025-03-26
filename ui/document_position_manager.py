import logging
from typing import Optional, Any

from PyQt6.QtWidgets import QTabWidget
from PyQt6.QtWebEngineWidgets import QWebEngineView

from core.knowledge_base.models import Document

logger = logging.getLogger(__name__)

class DocumentPositionManager:
    """Manages document positions across tabs and views."""
    
    def __init__(self, db_session, content_tabs):
        """Initialize the document position manager.
        
        Args:
            db_session: SQLAlchemy database session
            content_tabs: QTabWidget containing document views
        """
        self.db_session = db_session
        self.content_tabs = content_tabs
    
    def save_document_position(self, document_id: int) -> bool:
        """Save the current position for a document.
        
        Args:
            document_id: ID of the document
            
        Returns:
            bool: True if position was saved successfully
        """
        try:
            position = self._get_current_position(document_id)
            
            if position is None:
                logger.warning(f"Couldn't determine position for document {document_id}")
                return False
            
            # Save position to database
            document = self.db_session.query(Document).get(document_id)
            if document:
                document.position = position
                self.db_session.commit()
                logger.info(f"Saved position {position} for document {document_id}")
                return True
            else:
                logger.warning(f"Document not found: {document_id}")
                return False
                
        except Exception as e:
            logger.exception(f"Error saving document position: {e}")
            return False
    
    def _find_document_view(self, document_id: int) -> Optional[Any]:
        """Find a document view in the tabs.
        
        Args:
            document_id: ID of the document to find
            
        Returns:
            Optional[Any]: The document view widget or None if not found
        """
        if not self.content_tabs:
            return None
            
        for i in range(self.content_tabs.count()):
            tab_widget = self.content_tabs.widget(i)
            
            # Check if it's a document view with the right ID
            if hasattr(tab_widget, 'document_id') and tab_widget.document_id == document_id:
                return tab_widget
                
        return None
    
    def _get_current_position(self, document_id: int) -> Optional[int]:
        """Get the current position for a document view.
        
        Args:
            document_id: ID of the document
            
        Returns:
            Optional[int]: The current position or None if not available
        """
        try:
            # Find the document view in open tabs
            tab_widget = self._find_document_view(document_id)
            
            if not tab_widget:
                logger.warning(f"Couldn't find open tab for document {document_id}")
                return None
            
            # Check if web_view exists and hasn't been deleted
            if hasattr(tab_widget, 'web_view'):
                try:
                    # Test if the object is still valid
                    if tab_widget.web_view.parent() is None:
                        # The widget has probably been deleted
                        logger.debug(f"QWebEngineView for document {document_id} appears to be deleted")
                        return None
                except RuntimeError:
                    # Handle the case where the C++ object has been deleted
                    logger.debug(f"QWebEngineView for document {document_id} has been deleted")
                    return None
                
                # Now it's safe to use the web_view
                return self._get_position_from_webview(tab_widget.web_view)
            
            # For other view types
            if hasattr(tab_widget, 'content_edit'):
                if isinstance(tab_widget.content_edit, QWebEngineView):
                    try:
                        # Test if the object is still valid
                        if tab_widget.content_edit.parent() is None:
                            logger.debug(f"QWebEngineView content_edit for document {document_id} appears to be deleted")
                            return None
                    except RuntimeError:
                        # Handle the case where the C++ object has been deleted
                        logger.debug(f"QWebEngineView content_edit for document {document_id} has been deleted")
                        return None
                    
                    # Now it's safe to use the content_edit
                    return self._get_position_from_webview(tab_widget.content_edit)
                elif hasattr(tab_widget.content_edit, 'verticalScrollBar'):
                    scrollbar = tab_widget.content_edit.verticalScrollBar()
                    return scrollbar.value()
            
            logger.warning(f"Unsupported document view type for position tracking")
            return None
            
        except Exception as e:
            logger.exception(f"Error getting current position: {e}")
            return None
    
    def _get_position_from_webview(self, web_view: QWebEngineView) -> Optional[int]:
        """Get the scroll position from a webview.
        
        Args:
            web_view: QWebEngineView instance
            
        Returns:
            Optional[int]: Scroll position or None if not available
        """
        try:
            # Store a reference to self for callback
            position_manager = self
            
            # We need to use a synchronous approach to get the position
            # since we can't use callbacks properly here
            try:
                # First check if we have a cached position in the webview
                if hasattr(web_view, 'last_known_position'):
                    return web_view.last_known_position
                    
                # For document views, they might track position on their own
                if hasattr(web_view.parent(), 'last_scroll_position'):
                    return web_view.parent().last_scroll_position
                    
                # Otherwise use parent document's stored position as fallback
                if hasattr(web_view.parent(), 'document_id'):
                    document_id = web_view.parent().document_id
                    document = self.db_session.query(Document).get(document_id)
                    if document and document.position is not None:
                        return document.position
            except (RuntimeError, AttributeError) as e:
                logger.debug(f"Error accessing WebView properties: {e}")
                
            # If we don't have a cached position, return last known position from DB
            if hasattr(web_view.parent(), 'document_id'):
                document_id = web_view.parent().document_id
                document = self.db_session.query(Document).get(document_id)
                if document and document.position is not None:
                    return document.position
            
            # Fallback to default
            return 0
            
        except Exception as e:
            logger.exception(f"Error getting position from webview: {e}")
            return None 