import os
import logging
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import json
import time
import tempfile
from io import BytesIO
from pathlib import Path
import base64
import re
import zipfile
import io
import shutil
import requests
from urllib.parse import urlparse

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QScrollArea, QSplitter, QTextEdit,
    QToolBar, QMenu, QMessageBox, QApplication, QDialog,
    QSizePolicy, QTabWidget, QApplication, QStyle, QComboBox
)

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QPoint, QUrl, QObject, QTimer, QSize, QEvent
from PyQt6.QtGui import QAction, QTextCursor, QColor, QTextCharFormat, QIcon, QAction
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEngineSettings
    from PyQt6.QtWebChannel import QWebChannel
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False

from core.knowledge_base.models import Document, Extract, WebHighlight
from core.content_extractor.extractor import ContentExtractor
from core.document_processor.handlers.epub_handler import EPUBHandler
from .document_extracts_view import DocumentExtractsView
from .load_epub_helper import setup_epub_webview
from .load_youtube_helper import setup_youtube_webview, extract_video_id_from_document
from .youtube_transcript_view import YouTubeTranscriptView
from core.spaced_repetition.incremental_reading import IncrementalReadingManager

logger = logging.getLogger(__name__)

class WebViewCallback(QObject):
    """Callback handler for JavaScript communication with WebView."""
    
    def __init__(self, document_view):
        """Initialize with document view reference."""
        super().__init__()
        self.document_view = document_view
    
    @pyqtSlot(str)
    def selectionChanged(self, text):
        """Handle text selection changes from WebView."""
        if self.document_view:
            self.document_view._handle_webview_selection(text)
    
    @pyqtSlot(str)
    def extractText(self, text):
        """Handle text extraction requests from WebView."""
        if self.document_view and text:
            self.document_view._handle_sm_extract_result(text)
    
    @pyqtSlot(str)
    def createCloze(self, text):
        """Handle cloze creation requests from WebView."""
        if self.document_view and text:
            self.document_view._handle_sm_cloze_result(text)
    
    @pyqtSlot()
    def skipItem(self):
        """Handle skip item requests from WebView."""
        if self.document_view:
            # This would connect to review scheduling
            pass

class VimKeyHandler:
    """Helper class for handling Vim-like key bindings."""
    
    def __init__(self, document_view):
        self.document_view = document_view
        self.vim_mode = True  # Default to Vim mode on
        self.command_mode = False  # Normal mode by default (not command mode)
        self.visual_mode = False  # Not in visual mode by default
        self.current_command = ""
        self.count_prefix = ""  # For number prefixes like 5j
        self.selection_start = None  # For visual mode selection
        self.selection_active = False
        
    def toggle_vim_mode(self):
        """Toggle Vim mode on/off."""
        self.vim_mode = not self.vim_mode
        if not self.vim_mode:
            self.command_mode = False
            self.visual_mode = False
            self.current_command = ""
        logger.debug(f"Vim mode {'enabled' if self.vim_mode else 'disabled'}")
        return self.vim_mode
        
    def handle_key_event(self, event):
        """Handle key events in Vim style."""
        if not self.vim_mode:
            return False
            
        # Get key information
        key = event.key()
        text = event.text()
        modifiers = event.modifiers()
        
        # Handle visual mode specially
        if self.visual_mode:
            return self._handle_visual_mode(key, text, modifiers)
            
        # Handle count prefix (numbers before commands)
        if not self.command_mode and text.isdigit() and self.count_prefix != "0":  # Don't start with 0
            self.count_prefix += text
            return True
            
        # Get count (default to 1 if no prefix)
        count = int(self.count_prefix) if self.count_prefix else 1
        
        # Handle command mode (after : key)
        if self.command_mode:
            if key == Qt.Key.Key_Escape:
                self.command_mode = False
                self.current_command = ""
                return True
            elif key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
                self._execute_command(self.current_command)
                self.command_mode = False
                self.current_command = ""
                return True
            elif key == Qt.Key.Key_Backspace:
                self.current_command = self.current_command[:-1]
                return True
            else:
                self.current_command += text
                return True
        
        # Enter visual mode with v
        if key == Qt.Key.Key_V:
            self._enter_visual_mode()
            self.count_prefix = ""
            return True
                
        # Handle normal mode keys
        if key == Qt.Key.Key_J:  # j - move down
            self._scroll_down(count)
            self.count_prefix = ""
            return True
            
        elif key == Qt.Key.Key_K:  # k - move up
            self._scroll_up(count)
            self.count_prefix = ""
            return True
            
        elif key == Qt.Key.Key_G:  # g - go to top/bottom
            if modifiers & Qt.KeyboardModifier.ShiftModifier:  # G - go to bottom
                self._scroll_to_bottom()
            else:  # g - go to top
                self._scroll_to_top()
            self.count_prefix = ""
            return True
            
        elif key == Qt.Key.Key_D:  # d - half page down
            if modifiers & Qt.KeyboardModifier.ControlModifier:  # Ctrl+d
                self._scroll_half_page_down()
                self.count_prefix = ""
                return True
                
        elif key == Qt.Key.Key_U:  # u - half page up
            if modifiers & Qt.KeyboardModifier.ControlModifier:  # Ctrl+u
                self._scroll_half_page_up()
                self.count_prefix = ""
                return True
                
        elif key == Qt.Key.Key_F:  # f - page down
            if modifiers & Qt.KeyboardModifier.ControlModifier:  # Ctrl+f
                self._scroll_page_down()
                self.count_prefix = ""
                return True
                
        elif key == Qt.Key.Key_B:  # b - page up
            if modifiers & Qt.KeyboardModifier.ControlModifier:  # Ctrl+b
                self._scroll_page_up()
                self.count_prefix = ""
                return True
                
        elif key == Qt.Key.Key_Slash:  # / - search
            # TODO: Implement search functionality
            self.count_prefix = ""
            return True
            
        elif key == Qt.Key.Key_Colon:  # : - command mode
            self.command_mode = True
            self.current_command = ""
            self.count_prefix = ""
            return True
            
        elif key == Qt.Key.Key_Escape:  # ESC - clear state
            self.count_prefix = ""
            return True
            
        # If we've gotten this far and still have a count_prefix, it wasn't used,
        # so we should clear it
        self.count_prefix = ""
        return False
    
    def _handle_visual_mode(self, key, text, modifiers):
        """Handle key events while in visual mode."""
        # Exit visual mode with Escape
        if key == Qt.Key.Key_Escape:
            self._exit_visual_mode()
            return True
            
        # Extract text with 'e'
        if key == Qt.Key.Key_E:
            self._extract_selected_text()
            self._exit_visual_mode()
            return True
            
        # Flashcard with 'f'
        if key == Qt.Key.Key_F:
            self._create_flashcard()
            self._exit_visual_mode()
            return True
            
        # Cloze deletion with 'c'
        if key == Qt.Key.Key_C:
            self._create_cloze_deletion()
            self._exit_visual_mode()
            return True
            
        # Movement keys to extend selection
        if key == Qt.Key.Key_H:  # left
            self._extend_selection_left()
            return True
            
        if key == Qt.Key.Key_J:  # down
            self._extend_selection_down()
            return True
            
        if key == Qt.Key.Key_K:  # up
            self._extend_selection_up()
            return True
            
        if key == Qt.Key.Key_L:  # right
            self._extend_selection_right()
            return True
            
        if key == Qt.Key.Key_W:  # word forward
            self._extend_selection_word_forward()
            return True
            
        if key == Qt.Key.Key_B:  # word backward
            self._extend_selection_word_backward()
            return True
            
        return True  # Consume all keys in visual mode
    
    def _enter_visual_mode(self):
        """Enter visual mode for text selection."""
        self.visual_mode = True
        logger.debug("Entering visual mode")
        
        content_edit = self.document_view.content_edit
        
        # Setup based on content type
        if isinstance(content_edit, QTextEdit):
            # For text edit, ensure cursor is visible
            cursor = content_edit.textCursor()
            self.selection_start = cursor.position()
            content_edit.ensureCursorVisible()
            
            # Set a different cursor shape to indicate visual mode
            content_edit.viewport().setCursor(Qt.CursorShape.IBeamCursor)
            
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            # For web view, set cursor style with JavaScript
            script = """
            document.body.style.cursor = 'text';
            
            // Create selection markers
            const marker = document.createElement('div');
            marker.id = 'vim-cursor-marker';
            marker.style.position = 'absolute';
            marker.style.width = '2px';
            marker.style.height = '1.2em';
            marker.style.backgroundColor = 'rgba(255, 0, 0, 0.7)';
            marker.style.zIndex = '9999';
            
            // Add to document
            document.body.appendChild(marker);
            
            // Position at beginning of first text node we can find
            const textNodes = [];
            function findTextNodes(node) {
                if (node.nodeType === Node.TEXT_NODE && node.textContent.trim().length > 0) {
                    textNodes.push(node);
                } else {
                    for (let i = 0; i < node.childNodes.length; i++) {
                        findTextNodes(node.childNodes[i]);
                    }
                }
            }
            
            findTextNodes(document.body);
            
            // If we found any text nodes, create a selection
            if (textNodes.length > 0) {
                const range = document.createRange();
                range.setStart(textNodes[0], 0);
                range.setEnd(textNodes[0], 0);
                
                const selection = window.getSelection();
                selection.removeAllRanges();
                selection.addRange(range);
                
                // Position marker at selection start
                const rect = range.getBoundingClientRect();
                marker.style.left = rect.left + 'px';
                marker.style.top = rect.top + 'px';
                
                // Store initial position in a way we can access later
                window.vimVisualModeStart = {
                    node: textNodes[0],
                    offset: 0
                };
            }
            """
            content_edit.page().runJavaScript(script)
        
        # Update the mode display
        self.document_view.vim_status_label.setText("Vim Mode: Visual")
        
    def _exit_visual_mode(self):
        """Exit visual mode."""
        self.visual_mode = False
        logger.debug("Exiting visual mode")
        
        content_edit = self.document_view.content_edit
        
        # Reset cursor/selection based on content type
        if isinstance(content_edit, QTextEdit):
            # Reset cursor shape
            content_edit.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            # Reset cursor and remove visual markers with JavaScript
            script = """
            document.body.style.cursor = 'auto';
            
            // Remove any selection marker
            const marker = document.getElementById('vim-cursor-marker');
            if (marker) {
                marker.parentNode.removeChild(marker);
            }
            
            // Clear selection
            window.getSelection().removeAllRanges();
            delete window.vimVisualModeStart;
            """
            content_edit.page().runJavaScript(script)
        
        # Update mode display
        self.document_view.vim_status_label.setText("Vim Mode: Normal")
    
    def _scroll_down(self, count=1):
        """Scroll down by count lines."""
        content_edit = self.document_view.content_edit
        
        # Handle different widget types
        if isinstance(content_edit, QTextEdit):
            scrollbar = content_edit.verticalScrollBar()
            if scrollbar:
                # Use line height as scroll unit
                line_height = content_edit.fontMetrics().height()
                scrollbar.setValue(scrollbar.value() + count * line_height)
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            # For web view, use JavaScript to scroll
            script = f"window.scrollBy(0, {count * 30});"  # 30px per line
            content_edit.page().runJavaScript(script)
        
    def _scroll_up(self, count=1):
        """Scroll up by count lines."""
        content_edit = self.document_view.content_edit
        
        # Handle different widget types
        if isinstance(content_edit, QTextEdit):
            scrollbar = content_edit.verticalScrollBar()
            if scrollbar:
                # Use line height as scroll unit
                line_height = content_edit.fontMetrics().height()
                scrollbar.setValue(scrollbar.value() - count * line_height)
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            # For web view, use JavaScript to scroll
            script = f"window.scrollBy(0, -{count * 30});"  # 30px per line
            content_edit.page().runJavaScript(script)
    
    def _scroll_to_top(self):
        """Scroll to the top of the document."""
        content_edit = self.document_view.content_edit
        
        if isinstance(content_edit, QTextEdit):
            # For text edit, move cursor to start and ensure visible
            cursor = content_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            content_edit.setTextCursor(cursor)
            content_edit.ensureCursorVisible()
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            # For web view, use JavaScript to scroll to top
            script = "window.scrollTo(0, 0);"
            content_edit.page().runJavaScript(script)
    
    def _scroll_to_bottom(self):
        """Scroll to the bottom of the document."""
        content_edit = self.document_view.content_edit
        
        if isinstance(content_edit, QTextEdit):
            # For text edit, move cursor to end and ensure visible
            cursor = content_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            content_edit.setTextCursor(cursor)
            content_edit.ensureCursorVisible()
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            # For web view, use JavaScript to scroll to bottom
            script = "window.scrollTo(0, document.body.scrollHeight);"
            content_edit.page().runJavaScript(script)
    
    def _scroll_half_page_down(self):
        """Scroll down half a page (Ctrl+d in Vim)."""
        content_edit = self.document_view.content_edit
        
        if isinstance(content_edit, QTextEdit):
            scrollbar = content_edit.verticalScrollBar()
            if scrollbar:
                # Calculate half page height
                page_step = scrollbar.pageStep()
                scrollbar.setValue(scrollbar.value() + page_step // 2)
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            # For web view, use JavaScript to get window height and scroll
            script = "window.scrollBy(0, window.innerHeight / 2);"
            content_edit.page().runJavaScript(script)
    
    def _scroll_half_page_up(self):
        """Scroll up half a page (Ctrl+u in Vim)."""
        content_edit = self.document_view.content_edit
        
        if isinstance(content_edit, QTextEdit):
            scrollbar = content_edit.verticalScrollBar()
            if scrollbar:
                # Calculate half page height
                page_step = scrollbar.pageStep()
                scrollbar.setValue(scrollbar.value() - page_step // 2)
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            # For web view, use JavaScript to get window height and scroll
            script = "window.scrollBy(0, -window.innerHeight / 2);"
            content_edit.page().runJavaScript(script)
    
    def _scroll_page_down(self):
        """Scroll down a full page (Ctrl+f in Vim)."""
        content_edit = self.document_view.content_edit
        
        if isinstance(content_edit, QTextEdit):
            scrollbar = content_edit.verticalScrollBar()
            if scrollbar:
                # Use page step
                page_step = scrollbar.pageStep()
                scrollbar.setValue(scrollbar.value() + page_step)
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            # For web view, use JavaScript to get window height and scroll
            script = "window.scrollBy(0, window.innerHeight);"
            content_edit.page().runJavaScript(script)
    
    def _scroll_page_up(self):
        """Scroll up a full page (Ctrl+b in Vim)."""
        content_edit = self.document_view.content_edit
        
        if isinstance(content_edit, QTextEdit):
            scrollbar = content_edit.verticalScrollBar()
            if scrollbar:
                # Use page step
                page_step = scrollbar.pageStep()
                scrollbar.setValue(scrollbar.value() - page_step)
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            # For web view, use JavaScript to get window height and scroll
            script = "window.scrollBy(0, -window.innerHeight);"
            content_edit.page().runJavaScript(script)
    
    def _execute_command(self, command):
        """Execute a Vim-like command."""
        command = command.strip()
        
        if not command:
            return
            
        logger.debug(f"Executing Vim command: {command}")
        
        # Handle basic commands
        if command in ['q', 'quit']:
            # Close the document
            self.document_view.close()
        elif command.startswith('set '):
            # Handle settings
            setting = command[4:].strip()
            if setting == 'novim':
                self.toggle_vim_mode()
            elif setting == 'vim':
                self.vim_mode = True
        # Add more commands as needed
    
    def _extract_selected_text(self):
        """Extract the currently selected text."""
        content_edit = self.document_view.content_edit
        
        if isinstance(content_edit, QTextEdit):
            selected_text = content_edit.textCursor().selectedText()
            if selected_text:
                self.document_view.selected_text = selected_text
                self.document_view._on_create_extract()
                
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            # Use JavaScript to get selected text
            script = """
            window.getSelection().toString();
            """
            content_edit.page().runJavaScript(
                script,
                lambda text: self._handle_extract_from_webview(text)
            )
    
    def _handle_extract_from_webview(self, text):
        """Handle extract creation from web view selected text."""
        if text and text.strip():
            self.document_view.selected_text = text.strip()
            self.document_view._on_create_extract()
    
    def _create_flashcard(self):
        """Create a flashcard from selected text."""
        # This would require integration with a flashcard system
        # For now, we'll just extract the text
        self._extract_selected_text()
        
        # TODO: Add flashcard-specific handling when a flashcard system is available
        logger.debug("Flashcard creation requested - extracting text for now")
    
    def _create_cloze_deletion(self):
        """Create a cloze deletion from selected text."""
        # This would require integration with a flashcard/cloze system
        # For now, we'll just extract the text
        self._extract_selected_text()
        
        # TODO: Add cloze-specific handling when a cloze system is available
        logger.debug("Cloze deletion requested - extracting text for now")
    
    def _extend_selection_left(self):
        """Extend selection to the left."""
        content_edit = self.document_view.content_edit
        
        if isinstance(content_edit, QTextEdit):
            cursor = content_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor)
            content_edit.setTextCursor(cursor)
            
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            script = """
            const selection = window.getSelection();
            if (selection.rangeCount > 0) {
                const range = selection.getRangeAt(0);
                
                // Try to extend one character left
                try {
                    const startNode = range.startContainer;
                    const startOffset = range.startOffset;
                    
                    if (startOffset > 0) {
                        // Can move left within current node
                        range.setStart(startNode, startOffset - 1);
                    } else {
                        // Need to find previous text node
                        // This is simplified - would need more complex traversal for complete implementation
                    }
                    
                    // Update selection
                    selection.removeAllRanges();
                    selection.addRange(range);
                    
                    // Update marker
                    const marker = document.getElementById('vim-cursor-marker');
                    if (marker) {
                        const rect = range.getBoundingClientRect();
                        marker.style.left = rect.left + 'px';
                        marker.style.top = rect.top + 'px';
                    }
                } catch (e) {
                    console.error('Error extending selection left:', e);
                }
            }
            return window.getSelection().toString();
            """
            content_edit.page().runJavaScript(script)
    
    def _extend_selection_right(self):
        """Extend selection to the right."""
        content_edit = self.document_view.content_edit
        
        if isinstance(content_edit, QTextEdit):
            cursor = content_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor)
            content_edit.setTextCursor(cursor)
            
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            script = """
            const selection = window.getSelection();
            if (selection.rangeCount > 0) {
                const range = selection.getRangeAt(0);
                
                // Try to extend one character right
                try {
                    const endNode = range.endContainer;
                    const endOffset = range.endOffset;
                    
                    if (endNode.nodeType === Node.TEXT_NODE && endOffset < endNode.textContent.length) {
                        // Can move right within current text node
                        range.setEnd(endNode, endOffset + 1);
                    } else {
                        // Need to find next text node (simplified)
                    }
                    
                    // Update selection
                    selection.removeAllRanges();
                    selection.addRange(range);
                } catch (e) {
                    console.error('Error extending selection right:', e);
                }
            }
            return window.getSelection().toString();
            """
            content_edit.page().runJavaScript(script)
    
    def _extend_selection_up(self):
        """Extend selection upward."""
        content_edit = self.document_view.content_edit
        
        if isinstance(content_edit, QTextEdit):
            cursor = content_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Up, QTextCursor.MoveMode.KeepAnchor)
            content_edit.setTextCursor(cursor)
            
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            # This is quite complex in a web page - we'll use a simplified approach
            script = """
            const selection = window.getSelection();
            if (selection.rangeCount === 0) return '';
            
            // Get current range
            const range = selection.getRangeAt(0);
            
            // Create a point slightly above the start of current selection
            const startRect = range.getBoundingClientRect();
            const x = startRect.left;
            const y = startRect.top - 20; // Move up by approximate line height
            
            // Use document.caretPositionFromPoint or document.elementFromPoint
            let newNode, newOffset;
            
            if (document.caretPositionFromPoint) {
                const pos = document.caretPositionFromPoint(x, y);
                if (pos) {
                    newNode = pos.offsetNode;
                    newOffset = pos.offset;
                }
            } else if (document.elementFromPoint) {
                // Fallback method - less accurate
                const element = document.elementFromPoint(x, y);
                if (element && element.firstChild) {
                    newNode = element.firstChild;
                    newOffset = 0;
                }
            }
            
            // If we found a node, update selection
            if (newNode) {
                try {
                    // Create new range from new point to current end
                    const newRange = document.createRange();
                    newRange.setStart(newNode, newOffset);
                    newRange.setEnd(range.endContainer, range.endOffset);
                    
                    // Apply new selection
                    selection.removeAllRanges();
                    selection.addRange(newRange);
                } catch (e) {
                    console.error('Error extending selection up:', e);
                }
            }
            
            return selection.toString();
            """
            content_edit.page().runJavaScript(script)
    
    def _extend_selection_down(self):
        """Extend selection downward."""
        content_edit = self.document_view.content_edit
        
        if isinstance(content_edit, QTextEdit):
            cursor = content_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Down, QTextCursor.MoveMode.KeepAnchor)
            content_edit.setTextCursor(cursor)
            
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            # Similar approach to _extend_selection_up but in opposite direction
            script = """
            const selection = window.getSelection();
            if (selection.rangeCount === 0) return '';
            
            // Get current range
            const range = selection.getRangeAt(0);
            
            // Create a point slightly below the end of current selection
            const endRect = range.getBoundingClientRect();
            const x = endRect.right;
            const y = endRect.bottom + 20; // Move down by approximate line height
            
            // Use document.caretPositionFromPoint or document.elementFromPoint
            let newNode, newOffset;
            
            if (document.caretPositionFromPoint) {
                const pos = document.caretPositionFromPoint(x, y);
                if (pos) {
                    newNode = pos.offsetNode;
                    newOffset = pos.offset;
                }
            } else if (document.elementFromPoint) {
                // Fallback method - less accurate
                const element = document.elementFromPoint(x, y);
                if (element && element.firstChild) {
                    newNode = element.firstChild;
                    newOffset = 0;
                }
            }
            
            // If we found a node, update selection
            if (newNode) {
                try {
                    // Create new range from current start to new point
                    const newRange = document.createRange();
                    newRange.setStart(range.startContainer, range.startOffset);
                    newRange.setEnd(newNode, newOffset);
                    
                    // Apply new selection
                    selection.removeAllRanges();
                    selection.addRange(newRange);
                } catch (e) {
                    console.error('Error extending selection down:', e);
                }
            }
            
            return selection.toString();
            """
            content_edit.page().runJavaScript(script)
    
    def _extend_selection_word_forward(self):
        """Extend selection to the next word."""
        content_edit = self.document_view.content_edit
        
        if isinstance(content_edit, QTextEdit):
            cursor = content_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.NextWord, QTextCursor.MoveMode.KeepAnchor)
            content_edit.setTextCursor(cursor)
            
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            # Simplified word selection - better implementations would use text node traversal
            script = """
            const selection = window.getSelection();
            if (!selection.rangeCount) return '';
            
            const range = selection.getRangeAt(0);
            const endNode = range.endContainer;
            
            if (endNode.nodeType === Node.TEXT_NODE) {
                const text = endNode.textContent;
                const endOffset = range.endOffset;
                
                // Find next word boundary
                let nextSpace = text.indexOf(' ', endOffset);
                if (nextSpace === -1) nextSpace = text.length;
                
                // Extend to word boundary
                range.setEnd(endNode, nextSpace + 1);
                
                // Update selection
                selection.removeAllRanges();
                selection.addRange(range);
            }
            
            return selection.toString();
            """
            content_edit.page().runJavaScript(script)
    
    def _extend_selection_word_backward(self):
        """Extend selection to the previous word."""
        content_edit = self.document_view.content_edit
        
        if isinstance(content_edit, QTextEdit):
            cursor = content_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.PreviousWord, QTextCursor.MoveMode.KeepAnchor)
            content_edit.setTextCursor(cursor)
            
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            # Simplified word selection - better implementations would use text node traversal
            script = """
            const selection = window.getSelection();
            if (!selection.rangeCount) return '';
            
            const range = selection.getRangeAt(0);
            const startNode = range.startContainer;
            
            if (startNode.nodeType === Node.TEXT_NODE) {
                const text = startNode.textContent;
                const startOffset = range.startOffset;
                
                // Find previous word boundary
                const textBefore = text.substring(0, startOffset);
                let prevSpace = textBefore.lastIndexOf(' ');
                
                // If no space found, go to beginning of text
                if (prevSpace === -1) prevSpace = 0;
                else prevSpace += 1; // Move past the space
                
                // Extend selection
                range.setStart(startNode, prevSpace);
                
                // Update selection
                selection.removeAllRanges();
                selection.addRange(range);
            }
            
            return selection.toString();
            """
            content_edit.page().runJavaScript(script)

class DocumentView(QWidget):
    """UI component for viewing and processing documents."""
    
    extractCreated = pyqtSignal(int)  # extract_id
    navigate = pyqtSignal(str)  # navigation direction ("previous" or "next")
    
    def __init__(self, db_session, document_id=None):
        """Initialize DocumentView component."""
        super().__init__()
        
        # Store database session
        self.db_session = db_session
        
        # Document properties
        self.document_id = document_id
        self.document = None
        self.content_edit = None
        self.content_text = None
        self.selected_text = ""
        self.progress_marker = None
        self.zoom_level = 100
        self.view_mode = "Default"
        self.last_scroll_position = 0
        self.auto_save_interval = 5000  # 5 seconds
        
        # Initialize web channel for communication with JavaScript
        if HAS_WEBENGINE:
            from PyQt6.QtWebChannel import QWebChannel
            self.web_channel = QWebChannel()
        
        # Create auto-save timer
        self.auto_save_timer = QTimer(self)
        self.auto_save_timer.timeout.connect(self._auto_save_position)
        
        # Create UI components
        self._create_ui()
        
        # Load document if provided
        if document_id:
            self.load_document(document_id)
            
    def _auto_save_position(self):
        """Automatically save the current position."""
        try:
            if not hasattr(self, 'document_id') or not self.document_id:
                return
                
            # For web view, get current position via JavaScript
            if hasattr(self, 'web_view') and self.web_view:
                script = """
                (function() {
                    return window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;
                })();
                """
                self.web_view.page().runJavaScript(script, self._update_scroll_position)
            
            # For content edit with scrollbar
            elif hasattr(self, 'content_edit') and hasattr(self.content_edit, 'verticalScrollBar'):
                position = self.content_edit.verticalScrollBar().value()
                self._update_scroll_position(position)
                
        except Exception as e:
            logger.exception(f"Error in auto-save position: {e}")
            
    def _update_scroll_position(self, position):
        """Update the stored scroll position and save to document if needed."""
        try:
            # Skip if position is None or not a number
            if position is None or not isinstance(position, (int, float)):
                return
                
            # Round to integer
            position = int(position)
            
            # Store locally
            self.last_scroll_position = position
            
            # Update document in database (if position changed significantly)
            document = self.db_session.query(Document).get(self.document_id)
            if document:
                current_pos = document.position or 0
                # Only save if changed by more than 20 pixels to avoid excessive DB writes
                if abs(position - current_pos) > 20:
                    document.position = position
                    document.last_accessed = datetime.utcnow()
                    self.db_session.commit()
                    logger.debug(f"Auto-saved position {position} for document {self.document_id}")
        except Exception as e:
            logger.exception(f"Error updating scroll position: {e}")
            
    def _inject_position_tracking_js(self, web_view):
        """Inject JavaScript to track scroll position."""
        script = """
        (function() {
            // Track scroll position
            let lastScrollY = window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;
            let ticking = false;
            
            function savePosition() {
                if (!window.qt) return;
                
                const scrollY = window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;
                
                // Only update if changed
                if (Math.abs(scrollY - lastScrollY) > 5) {
                    lastScrollY = scrollY;
                    
                    if (!ticking) {
                        window.requestAnimationFrame(function() {
                            if (window.qt.webChannel && window.qt.webChannel.objects.selectionHandler) {
                                // Use qtWebChannel to communicate back to Qt
                                window.lastKnownPosition = scrollY;
                            }
                            ticking = false;
                        });
                        ticking = true;
                    }
                }
            }
            
            // Listen for scroll events
            document.addEventListener('scroll', savePosition, { passive: true });
            
            // Also track position on key events that might cause scrolling
            document.addEventListener('keydown', function(e) {
                // Delay slightly to let the browser scroll first
                setTimeout(savePosition, 100);
            }, { passive: true });
            
            // And when user clicks links that might jump within the document
            document.addEventListener('click', function(e) {
                setTimeout(savePosition, 100);
            }, { passive: true });
            
            console.log('Document position tracking enabled');
        })();
        """
        web_view.page().runJavaScript(script)
        
    def _init_auto_save_timer(self):
        """Initialize or restart the auto-save timer."""
        # Stop existing timer if running
        if self.auto_save_timer.isActive():
            self.auto_save_timer.stop()
            
        # Start the timer
        if hasattr(self, 'document_id') and self.document_id:
            self.auto_save_timer.start(self.auto_save_interval)
            logger.debug(f"Started auto-save timer for document {self.document_id}")
    
    def _create_ui(self):
        """Create the UI components."""
        # Main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Toolbar
        toolbar = self._create_toolbar()
        layout.addWidget(toolbar)
        
        # Content splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Document content area
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)  # Minimize spacing between elements
        
        # Content will be added dynamically based on document type
        
        splitter.addWidget(self.content_widget)
        
        # Extracts area
        self.extract_view = DocumentExtractsView(self.db_session)
        self.extract_view.extractSelected.connect(self._on_extract_selected)
        splitter.addWidget(self.extract_view)
        
        # Set initial sizes - give almost all space to the PDF content (95/5 split)
        splitter.setSizes([950, 50])
        
        # Make sure the split ratio is maintained when resizing
        splitter.setStretchFactor(0, 19)  # Content gets 19x the stretch of extracts
        splitter.setStretchFactor(1, 1)   # Extracts get 1x stretch factor
        
        layout.addWidget(splitter, 1)  # Add stretch factor of 1 to expand
        
        # Add Vim mode status bar - use minimal height
        self.vim_status_widget = QWidget()
        self.vim_status_widget.setMaximumHeight(20)  # Limit height
        vim_status_layout = QHBoxLayout(self.vim_status_widget)
        vim_status_layout.setContentsMargins(2, 1, 2, 1)  # Minimal margins
        
        self.vim_status_label = QLabel("Vim Mode: Normal")
        vim_status_layout.addWidget(self.vim_status_label)
        
        # Add vim command display
        self.vim_command_label = QLabel("")
        vim_status_layout.addWidget(self.vim_command_label)
        
        # Add visual mode indicator
        self.vim_visual_label = QLabel("")
        self.vim_visual_label.setStyleSheet("color: #c22;")  # Red text for visual mode
        vim_status_layout.addWidget(self.vim_visual_label)
        
        vim_status_layout.addStretch(1)  # Push everything to the left
        
        # Add keyboard shortcuts info
        self.vim_shortcuts_label = QLabel("v:visual e:extract f:flashcard c:cloze")
        self.vim_shortcuts_label.setStyleSheet("color: #666; font-size: 9pt;")
        vim_status_layout.addWidget(self.vim_shortcuts_label)
        
        layout.addWidget(self.vim_status_widget)
        self.vim_status_widget.setVisible(False)  # Hide by default
        
        self.setLayout(layout)
        
        # Initialize Vim key handler
        self.vim_key_handler = VimKeyHandler(self)
    
    def _clear_content_layout(self):
        """Clear the content layout of any widgets."""
        try:
            # Stop audio playback if there's an audio player
            if hasattr(self, 'audio_player') and self.audio_player is not None:
                try:
                    # Stop playback and save position
                    self.audio_player.stop()
                    self.audio_player.save_position()
                    logger.info("Audio player stopped and position saved")
                except Exception as e:
                    logger.error(f"Error stopping audio player: {e}")
                
                # Clear reference to audio player
                self.audio_player = None

            # Clear the content layout
            if self.content_layout:
                while self.content_layout.count():
                    item = self.content_layout.takeAt(0)
                    widget = item.widget()
                    if widget:
                        widget.hide()
                        widget.deleteLater()
        except Exception as e:
            logger.error(f"Error clearing content layout: {e}")
    
    def _update_vim_status_visibility(self):
        """Update the visibility of the Vim status bar based on Vim mode state."""
        self.vim_status_widget.setVisible(self.vim_key_handler.vim_mode)
    
    def _toggle_vim_mode(self):
        """Toggle Vim mode on/off."""
        is_enabled = self.vim_key_handler.toggle_vim_mode()
        self.vim_toggle_action.setChecked(is_enabled)
        self._update_vim_status_visibility()
    
    def keyPressEvent(self, event):
        """Handle key press events for document view."""
        # Check for Ctrl+E shortcut for extract
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_E:
            self._on_extract()
            return
            
        # Check if Vim handler wants to handle this key
        if hasattr(self, 'vim_key_handler') and self.vim_key_handler.handle_key_event(event):
            # Update command display if in command mode
            if self.vim_key_handler.command_mode:
                self.vim_status_label.setText("Vim Mode: Command")
                self.vim_command_label.setText(":" + self.vim_key_handler.current_command)
                self.vim_visual_label.setText("")
            elif self.vim_key_handler.visual_mode:
                self.vim_status_label.setText("Vim Mode: Visual")
                self.vim_command_label.setText("")
                self.vim_visual_label.setText("[Selection Mode]")
            else:
                self.vim_status_label.setText("Vim Mode: Normal")
                self.vim_visual_label.setText("")
                # Show count prefix if any
                if self.vim_key_handler.count_prefix:
                    self.vim_command_label.setText(self.vim_key_handler.count_prefix)
                else:
                    self.vim_command_label.setText("")
            
            return
            
        # Allow the parent class to handle the event
        super().keyPressEvent(event)
    
    def _create_webview_and_setup(self, html_content, base_url):
        """Create a web view with the given HTML content and set it up for use."""
        if not HAS_WEBENGINE:
            raise Exception("WebEngine is not available")
            
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtCore import QUrl, QTimer
        
        # Create web view
        web_view = QWebEngineView()
        web_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Set up web channel for JavaScript communication if needed
        if not hasattr(self, 'web_channel'):
            from PyQt6.QtWebChannel import QWebChannel
            self.web_channel = QWebChannel()
        
        # Track references to prevent garbage collection
        self.keep_alive(web_view)
        
        # Set up the content
        if html_content:
            # Process HTML content with any needed enhancements
            html_content = self._inject_javascript_libraries(html_content)
            
            # Load the HTML content with the base URL
            web_view.setHtml(html_content, base_url)
        
        # Track selection changes if the document supports text selection
        class SelectionHandler(QObject):
            @pyqtSlot(str)
            def selectionChanged(self, text):
                self.parent().selected_text = text
                if hasattr(self.parent(), 'extract_button'):
                    self.parent().extract_button.setEnabled(bool(text and len(text.strip()) > 0))
        
        # Create selection handler
        handler = SelectionHandler(self)
        web_view.page().setWebChannel(self.web_channel)
        self.web_channel.registerObject("selectionHandler", handler)
        
        # Add method to check for selection
        def check_selection():
            web_view.page().runJavaScript(
                """
                (function() {
                    var selection = window.getSelection();
                    var text = selection.toString();
                    return text || window.text_selection || '';
                })();
                """,
                self._handle_webview_selection
            )
        
        # Store method for later use
        web_view.check_selection = check_selection
        
        # Set up context menu
        def context_menu_wrapper(pos):
            # Check for selection first
            check_selection()
            # Process events to ensure we get the selection
            QApplication.processEvents()
            # Small delay to ensure selection is processed
            QTimer.singleShot(50, lambda: self._on_content_menu(pos))
        
        # Connect context menu
        web_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        web_view.customContextMenuRequested.connect(context_menu_wrapper)
        
        # Add position tracking
        web_view.loadFinished.connect(lambda ok: self._inject_position_tracking_js(web_view))
        
        return web_view
    
    def _handle_webview_selection(self, result):
        """Handle selection from web view JavaScript."""
        if result and isinstance(result, str):
            self.selected_text = result
            if hasattr(self, 'extract_button'):
                self.extract_button.setEnabled(bool(result and len(result.strip()) > 0))
    
    def _inject_position_tracking_js(self, web_view):
        """Inject JavaScript to track scrolling position in web view."""
        js_code = """
        (function() {
            // Set up scroll position tracking
            var lastPosition = 0;
            var scrollableElement = document.scrollingElement || document.documentElement;
            
            // Function to get normalized position (0-1)
            function getNormalizedPosition() {
                var maxScroll = scrollableElement.scrollHeight - scrollableElement.clientHeight;
                if (maxScroll <= 0) return 0;
                
                var currentPos = scrollableElement.scrollTop;
                return currentPos / maxScroll;
            }
            
            // Save position periodically
            window.setInterval(function() {
                var newPosition = getNormalizedPosition();
                if (Math.abs(newPosition - lastPosition) > 0.01) {
                    lastPosition = newPosition;
                    if (window.qt && window.qt.savePosition) {
                        window.qt.savePosition(newPosition);
                    }
                }
            }, 5000);
            
            // Set up position object
            if (!window.qt) window.qt = {};
            
            // Add a function to restore position
            window.qt.restorePosition = function(position) {
                if (position >= 0 && position <= 1) {
                    var maxScroll = scrollableElement.scrollHeight - scrollableElement.clientHeight;
                    scrollableElement.scrollTop = position * maxScroll;
                    lastPosition = position;
                    return true;
                }
                return false;
            };
            
            // Notify that initialization is complete
            if (window.qt && window.qt.positionTrackingReady) {
                window.qt.positionTrackingReady();
            }
            
            return "Position tracking initialized";
        })();
        """
        
        # Execute the JavaScript
        web_view.page().runJavaScript(js_code, lambda result: logger.debug(f"Position tracking result: {result}"))
        
        # Set up position handler if needed
        class PositionHandler(QObject):
            @pyqtSlot(float)
            def savePosition(self, position):
                self.parent()._save_document_position(position)
                
            @pyqtSlot()
            def positionTrackingReady(self):
                self.parent()._restore_webview_position()
        
        # Create handler if needed
        if not hasattr(self, 'position_handler'):
            self.position_handler = PositionHandler(self)
            self.web_channel.registerObject("positionHandler", self.position_handler)
    
    def _restore_webview_position(self):
        """Restore saved position in a web view."""
        if hasattr(self, 'document') and self.document and hasattr(self, 'web_view'):
            position = getattr(self.document, 'position', 0) or 0
            
            if position > 0:
                js_code = f"window.qt.restorePosition({position});"
                self.web_view.page().runJavaScript(js_code, lambda result: logger.debug(f"Restore position result: {result}"))
    
    def _on_extract(self):
        """Create extract from selected text."""
        try:
            if not hasattr(self, 'document_id') or not self.document_id:
                logger.warning("No document loaded")
                return
            
            # Get the selected highlight color
            color_name = self.highlight_color_combo.currentData()
                
            # Get selected text
            selected_text = None
            if hasattr(self, 'web_view') and self.web_view:
                # For web view, use JavaScript to get selected text
                script = f"""
                (function() {{
                    var selection = window.getSelection();
                    var text = selection.toString();
                    if (text && text.trim().length > 0) {{
                        // Highlight if we have a SuperMemo script
                        if (typeof highlightExtractedText === 'function') {{
                            highlightExtractedText('{color_name}');
                        }}
                        return text;
                    }}
                    return '';
                }})();
                """
                self.web_view.page().runJavaScript(
                    script,
                    lambda result: self._process_extracted_text(result, color_name)
                )
                # Continue processing in the callback (_process_extracted_text)
                return
            elif hasattr(self, 'text_edit') and self.text_edit:
                # For text edit, use cursor
                selected_text = self.text_edit.textCursor().selectedText()
                self._process_extracted_text(selected_text, color_name)
                
        except Exception as e:
            logger.exception(f"Error creating extract: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred: {str(e)}"
            )
            
    def _process_extracted_text(self, selected_text, color_name='yellow'):
        """Process text after extraction from web view or text edit."""
        try:
            if not selected_text or len(selected_text.strip()) < 5:
                QMessageBox.warning(
                    self, "Extract", 
                    "Please select some text to extract."
                )
                return
                
            # Create extract directly
            from core.knowledge_base.models import Extract
            
            extract = Extract(
                document_id=self.document_id,
                content=selected_text,
                created_date=datetime.utcnow(),
                priority=50
            )
            
            # Save extract
            self.db_session.add(extract)
            self.db_session.commit()
            
            # Also create a WebHighlight with the specified color
            from core.knowledge_base.models import WebHighlight
            
            highlight = WebHighlight(
                document_id=self.document_id,
                content=selected_text,
                created_date=datetime.utcnow(),
                color=color_name
            )
            
            # Save highlight
            self.db_session.add(highlight)
            self.db_session.commit()
            
            # Emit signal for extract created
            self.extractCreated.emit(extract.id)
            
            QMessageBox.information(
                self, "Extract", 
                "Extract created successfully. You can find it in the Knowledge Base."
            )
                
        except Exception as e:
            logger.exception(f"Error creating extract: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred: {str(e)}"
            )

    def _show_context_menu(self, position):
        """Show document context menu."""
        if not hasattr(self, 'document_id') or not self.document_id:
            return
            
        menu = QMenu(self)
        
        # Add export actions
        export_menu = QMenu("Export", menu)
        
        # Export extracts action
        export_extracts_action = QAction("Export Extracts", export_menu)
        export_extracts_action.triggered.connect(self._export_extracts)
        export_menu.addAction(export_extracts_action)
        
        # Export SuperMemo HTML action
        export_sm_html_action = QAction("Export SuperMemo HTML", export_menu)
        export_sm_html_action.triggered.connect(self._export_supermemo_html)
        export_menu.addAction(export_sm_html_action)
        
        menu.addMenu(export_menu)
        
        # Add document management actions
        menu.addSeparator()
        
        # Other actions...
        
        menu.exec(self.mapToGlobal(position))

    def _export_supermemo_html(self):
        """Export document extracts and highlights as SuperMemo-compatible HTML."""
        try:
            if not hasattr(self, 'document_id') or not self.document_id:
                logger.warning("No document loaded")
                return
                
            from PyQt6.QtWidgets import QFileDialog
            from core.spaced_repetition.sm_html_exporter import SuperMemoHTMLExporter
            
            # Ask for output directory
            output_dir = QFileDialog.getExistingDirectory(
                self, "Select Output Directory", os.path.expanduser("~")
            )
            
            if not output_dir:
                return
                
            # Export HTML
            exporter = SuperMemoHTMLExporter(self.db_session)
            result = exporter.export_document_extracts(self.document_id, output_dir)
            
            if result:
                QMessageBox.information(
                    self, "Export Successful", 
                    f"SuperMemo HTML exported to:\n{result}"
                )
            else:
                QMessageBox.warning(
                    self, "Export Failed", 
                    "Failed to export SuperMemo HTML. Check if there are extracts or highlights."
                )
                
        except Exception as e:
            logger.exception(f"Error exporting SuperMemo HTML: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred: {str(e)}"
            )

    def _add_supermemo_features(self, web_view):
        """Add SuperMemo-style incremental reading features to web view."""
        if not HAS_WEBENGINE or not isinstance(web_view, QWebEngineView):
            logger.warning("Cannot add SuperMemo features without WebEngine")
            return
            
        # Add JavaScript to enable SM-18 style incremental reading capabilities
        sm_script = """
        // SuperMemo SM-18 style incremental reading script
        
        // Initialize state
        let smState = {
            highlighting: false,
            startPoint: null,
            selectedText: '',
            lastSelection: null
        };
        
        // Add SuperMemo style toolbar
        function addSuperMemoToolbar() {
            // Create toolbar
            const toolbar = document.createElement('div');
            toolbar.id = 'sm-toolbar';
            toolbar.style.position = 'fixed';
            toolbar.style.bottom = '20px';
            toolbar.style.right = '20px';
            toolbar.style.zIndex = '1000';
            toolbar.style.backgroundColor = 'rgba(50, 50, 50, 0.7)';
            toolbar.style.padding = '5px';
            toolbar.style.borderRadius = '5px';
            toolbar.style.display = 'none';
            
            // Extract button
            const extractBtn = document.createElement('button');
            extractBtn.innerText = 'Extract';
            extractBtn.style.marginRight = '5px';
            extractBtn.style.cursor = 'pointer';
            extractBtn.onclick = function() {
                if (smState.selectedText) {
                    // Call back to Qt
                    if (typeof window.callbackHandler !== 'undefined') {
                        window.callbackHandler.extractText(smState.selectedText);
                    }
                    
                    // Highlight the extracted text
                    highlightExtractedText();
                    
                    // Visual feedback
                    extractBtn.style.backgroundColor = '#8f8';
                    setTimeout(() => {
                        extractBtn.style.backgroundColor = '';
                    }, 500);
                }
            };
            
            // Cloze button
            const clozeBtn = document.createElement('button');
            clozeBtn.innerText = 'Cloze';
            clozeBtn.style.marginRight = '5px';
            clozeBtn.style.cursor = 'pointer';
            clozeBtn.onclick = function() {
                if (smState.selectedText) {
                    // Call back to Qt
                    if (typeof window.callbackHandler !== 'undefined') {
                        window.callbackHandler.createCloze(smState.selectedText);
                    }
                    
                    // Visual feedback
                    clozeBtn.style.backgroundColor = '#8f8';
                    setTimeout(() => {
                        clozeBtn.style.backgroundColor = '';
                    }, 500);
                }
            };
            
            // Skip button
            const skipBtn = document.createElement('button');
            skipBtn.innerText = 'Skip';
            skipBtn.style.cursor = 'pointer';
            skipBtn.onclick = function() {
                // Call back to Qt
                if (typeof window.callbackHandler !== 'undefined') {
                    window.callbackHandler.skipItem();
                }
                
                // Visual feedback
                skipBtn.style.backgroundColor = '#f88';
                setTimeout(() => {
                    skipBtn.style.backgroundColor = '';
                }, 500);
            };
            
            // Add buttons to toolbar
            toolbar.appendChild(extractBtn);
            toolbar.appendChild(clozeBtn);
            toolbar.appendChild(skipBtn);
            
            // Add toolbar to document
            document.body.appendChild(toolbar);
            
            return toolbar;
        }
        
        // Track text selection
        document.addEventListener('selectionchange', function() {
            const selection = window.getSelection();
            const text = selection.toString().trim();
            
            // Store selection
            smState.selectedText = text;
            smState.lastSelection = selection;
            
            // Update toolbar visibility
            const toolbar = document.getElementById('sm-toolbar');
            if (toolbar) {
                if (text) {
                    // Position toolbar near selection
                    if (selection.rangeCount > 0) {
                        const range = selection.getRangeAt(0);
                        const rect = range.getBoundingClientRect();
                        
                        // Position near selection but ensure it's visible
                        toolbar.style.display = 'block';
                        toolbar.style.bottom = 'auto';
                        toolbar.style.right = 'auto';
                        
                        // Position above selection if there's room, otherwise below
                        if (rect.top > 100) {
                            toolbar.style.top = (rect.top - 40) + 'px';
                        } else {
                            toolbar.style.top = (rect.bottom + 10) + 'px';
                        }
                        
                        // Center horizontally on selection
                        toolbar.style.left = (rect.left + rect.width/2 - toolbar.offsetWidth/2) + 'px';
                    }
                } else {
                    toolbar.style.display = 'none';
                }
            }
            
            // Send selection to Qt if we have a callback handler
            if (text && typeof window.callbackHandler !== 'undefined') {
                window.callbackHandler.selectionChanged(text);
            }
        });
        
        // Run when document is loaded
        document.addEventListener('DOMContentLoaded', function() {
            // Add toolbar
            addSuperMemoToolbar();
            
            // Add keyboard shortcuts
            document.addEventListener('keydown', function(event) {
                // Handle Ctrl+E for extract
                if (event.ctrlKey && event.key === 'e') {
                    event.preventDefault();
                    const extractBtn = document.querySelector('#sm-toolbar button:nth-child(1)');
                    if (extractBtn) extractBtn.click();
                }
                
                // Handle Ctrl+C for cloze
                if (event.ctrlKey && event.key === 'c' && event.altKey) {
                    event.preventDefault();
                    const clozeBtn = document.querySelector('#sm-toolbar button:nth-child(2)');
                    if (clozeBtn) clozeBtn.click();
                }
                
                // Handle Ctrl+S for skip
                if (event.ctrlKey && event.key === 's') {
                    event.preventDefault();
                    const skipBtn = document.querySelector('#sm-toolbar button:nth-child(3)');
                    if (skipBtn) skipBtn.click();
                }
            });
        });
        
        // Function to highlight extracted text
        function highlightExtractedText() {
            if (!smState.lastSelection || !smState.lastSelection.rangeCount) return;
            
            const range = smState.lastSelection.getRangeAt(0);
            const span = document.createElement('span');
            span.className = 'extracted-text-highlight';
            span.style.backgroundColor = 'rgba(255, 255, 0, 0.3)';
            span.style.borderRadius = '2px';
            
            try {
                range.surroundContents(span);
                // Keep the selection active
                smState.lastSelection.removeAllRanges();
                smState.lastSelection.addRange(range);
            } catch (e) {
                console.error('Error highlighting text:', e);
            }
        }
        
        // Initialize right away if document is already loaded
        if (document.readyState === 'complete' || document.readyState === 'interactive') {
            setTimeout(function() {
                addSuperMemoToolbar();
            }, 100);
        }
        """
        
        # Inject the SuperMemo JavaScript
        web_view.page().runJavaScript(sm_script)
        
        # Connect JavaScript to handle selection changes
        # This is already set up in _create_webview_and_setup
        
        logger.debug("Added SuperMemo features to web view")
    
    def _restore_position(self):
        """Restore the saved document position."""
        if self.document and hasattr(self.document, 'position'):
            try:
                position = self.document.position
                
                # Different position restoration based on content type
                if position and position > 0:
                    if hasattr(self, 'web_view'):
                        # For web-based content
                        self._restore_webview_position()
                    elif hasattr(self, 'content_edit') and hasattr(self.content_edit, 'verticalScrollBar'):
                        # For scrollable widgets
                        scroll_bar = self.content_edit.verticalScrollBar()
                        if scroll_bar:
                            max_value = scroll_bar.maximum()
                            if max_value > 0:
                                target_pos = int(position * max_value)
                                scroll_bar.setValue(target_pos)
                                logger.debug(f"Restored position to {position} ({target_pos}/{max_value})")
                    
                    # Add other content type position restoration here
                    
                    return True
            except Exception as e:
                logger.exception(f"Error restoring position: {e}")
        
        return False
    
    def _save_document_position(self, position=None):
        """Save the current document position."""
        if not self.document or not self.db_session:
            return False
        
        try:
            # If position is not provided, calculate it
            if position is None:
                # For web content
                if hasattr(self, 'web_view'):
                    # Position should be saved by JavaScript callback
                    # Return early, nothing to do
                    return False
                
                # For scrollable widgets
                elif hasattr(self, 'content_edit') and hasattr(self.content_edit, 'verticalScrollBar'):
                    scroll_bar = self.content_edit.verticalScrollBar()
                    if scroll_bar:
                        max_value = scroll_bar.maximum()
                        if max_value > 0:
                            current_pos = scroll_bar.value()
                            position = current_pos / max_value
                        else:
                            position = 0
                
                # Add other content type position calculation here
                
                # If we couldn't calculate a position, return
                if position is None:
                    return False
            
            # Save position to document
            self.document.position = position
            
            # Save to database
            self.db_session.add(self.document)
            self.db_session.commit()
            
            logger.debug(f"Saved document position: {position}")
            return True
            
        except Exception as e:
            logger.exception(f"Error saving document position: {e}")
            return False

    def _handle_webview_selection(self, text):
        """Handle text selection in the WebView."""
        if text and text.strip():
            self.selected_text = text.strip()
            logger.debug(f"Selected text in WebView: {text[:50]}...")
            
    def _on_create_extract(self):
        """Create an extract from the selected text."""
        try:
            if not self.selected_text or len(self.selected_text.strip()) < 5:
                logger.warning("No text selected for extract creation")
                return
                
            # Create extract
            from core.knowledge_base.models import Extract
            
            extract = Extract(
                document_id=self.document_id,
                content=self.selected_text,
                created_date=datetime.utcnow(),
                priority=50  # Default priority
            )
            
            # Save extract
            self.db_session.add(extract)
            self.db_session.commit()
            
            # Emit the extract created signal
            self.extractCreated.emit(extract.id)
            
            logger.info(f"Created extract: {extract.id}")
            
            # Clear selection
            self.selected_text = ""
            
            return extract.id
            
        except Exception as e:
            logger.exception(f"Error creating extract: {e}")
            return None
            
    def _handle_sm_extract_result(self, text):
        """Handle extract creation from SuperMemo JS callback."""
        self.selected_text = text
        extract_id = self._on_create_extract()
        
        if extract_id:
            logger.info(f"Created extract from SuperMemo: {extract_id}")
            
            # Show visual feedback in web view if available
            if hasattr(self, 'web_view') and self.web_view:
                feedback_script = """
                // Show extract confirmation
                const feedback = document.createElement('div');
                feedback.textContent = 'Extract created!';
                feedback.style.position = 'fixed';
                feedback.style.top = '20px';
                feedback.style.left = '50%';
                feedback.style.transform = 'translateX(-50%)';
                feedback.style.backgroundColor = 'rgba(0, 200, 0, 0.8)';
                feedback.style.color = 'white';
                feedback.style.padding = '10px 20px';
                feedback.style.borderRadius = '5px';
                feedback.style.zIndex = '9999';
                feedback.style.fontWeight = 'bold';
                
                document.body.appendChild(feedback);
                
                // Remove after 2 seconds
                setTimeout(() => {
                    feedback.style.opacity = '0';
                    feedback.style.transition = 'opacity 0.5s';
                    setTimeout(() => feedback.remove(), 500);
                }, 2000);
                """
                self.web_view.page().runJavaScript(feedback_script)
        
    def _handle_sm_cloze_result(self, text):
        """Handle cloze creation from SuperMemo JS callback."""
        try:
            if not text or len(text.strip()) < 5:
                logger.warning("Text too short for cloze creation")
                return
                
            # Create cloze
            from core.knowledge_base.models import Extract
            
            # Mark this as a cloze extract using a special prefix
            cloze_content = f"[CLOZE] {text}"
            
            extract = Extract(
                document_id=self.document_id,
                content=cloze_content,
                created_date=datetime.utcnow(),
                priority=50,  # Default priority
                extract_type="cloze"
            )
            
            # Save extract
            self.db_session.add(extract)
            self.db_session.commit()
            
            # Emit the extract created signal
            self.extractCreated.emit(extract.id)
            
            logger.info(f"Created cloze extract: {extract.id}")
            
            # Show visual feedback in web view if available
            if hasattr(self, 'web_view') and self.web_view:
                feedback_script = """
                // Show cloze confirmation
                const feedback = document.createElement('div');
                feedback.textContent = 'Cloze created!';
                feedback.style.position = 'fixed';
                feedback.style.top = '20px';
                feedback.style.left = '50%';
                feedback.style.transform = 'translateX(-50%)';
                feedback.style.backgroundColor = 'rgba(0, 100, 200, 0.8)';
                feedback.style.color = 'white';
                feedback.style.padding = '10px 20px';
                feedback.style.borderRadius = '5px';
                feedback.style.zIndex = '9999';
                feedback.style.fontWeight = 'bold';
                
                document.body.appendChild(feedback);
                
                // Remove after 2 seconds
                setTimeout(() => {
                    feedback.style.opacity = '0';
                    feedback.style.transition = 'opacity 0.5s';
                    setTimeout(() => feedback.remove(), 500);
                }, 2000);
                """
                self.web_view.page().runJavaScript(feedback_script)
                
        except Exception as e:
            logger.exception(f"Error creating cloze: {e}")
            
    def _on_content_menu(self, position):
        """Show custom context menu for content."""
        try:
            menu = QMenu(self)
            
            # Check if we have selected text
            has_selection = False
            selected_text = ""
            
            # Define build_menu function first, before it's used
            def build_menu(has_selection, selected_text):
                # Store the selected text for use in action handlers
                self.selected_text = selected_text if has_selection else ""
                
                # Add extract action if text is selected
                if has_selection:
                    extract_action = QAction("Extract Selection", self)
                    extract_action.triggered.connect(self._extract_from_context_menu)
                    menu.addAction(extract_action)
                    
                    # Add highlight action with color submenu
                    highlight_menu = QMenu("Highlight Selection", menu)
                    
                    # Add color options
                    yellow_action = QAction("Yellow", self)
                    yellow_action.triggered.connect(lambda: self._highlight_with_color("yellow"))
                    highlight_menu.addAction(yellow_action)
                    
                    green_action = QAction("Green", self)
                    green_action.triggered.connect(lambda: self._highlight_with_color("green"))
                    highlight_menu.addAction(green_action)
                    
                    blue_action = QAction("Blue", self)
                    blue_action.triggered.connect(lambda: self._highlight_with_color("blue"))
                    highlight_menu.addAction(blue_action)
                    
                    pink_action = QAction("Pink", self)
                    pink_action.triggered.connect(lambda: self._highlight_with_color("pink"))
                    highlight_menu.addAction(pink_action)
                    
                    orange_action = QAction("Orange", self)
                    orange_action.triggered.connect(lambda: self._highlight_with_color("orange"))
                    highlight_menu.addAction(orange_action)
                    
                    menu.addMenu(highlight_menu)
                    
                    # Add separator
                    menu.addSeparator()
                else:
                    # If we're in a WebView and there's no selection, add a message
                    if hasattr(self, 'web_view') and self.web_view:
                        info_action = QAction("Select text to extract", self)
                        info_action.setEnabled(False)
                        menu.addAction(info_action)
                        menu.addSeparator()
                
                # Add document actions
                add_to_ir_action = QAction("Add to Incremental Reading", self)
                add_to_ir_action.triggered.connect(self._on_add_to_incremental_reading)
                menu.addAction(add_to_ir_action)
                
                mark_progress_action = QAction("Mark Reading Progress", self)
                mark_progress_action.triggered.connect(self._on_mark_reading_progress)
                menu.addAction(mark_progress_action)
                
                # Add zoom actions
                menu.addSeparator()
                
                zoom_in_action = QAction("Zoom In", self)
                zoom_in_action.triggered.connect(self._on_zoom_in)
                menu.addAction(zoom_in_action)
                
                zoom_out_action = QAction("Zoom Out", self)
                zoom_out_action.triggered.connect(self._on_zoom_out)
                menu.addAction(zoom_out_action)
            
            # Define context_menu_wrapper after build_menu is defined
            def context_menu_wrapper(text):
                if text and text.strip():
                    self.selected_text = text.strip()
                    has_selection = True
                    build_menu(True, text)
                    menu.exec(self.mapToGlobal(position))
                else:
                    # No selection, show basic menu
                    build_menu(False, "")
                    menu.exec(self.mapToGlobal(position))
            
            if hasattr(self, 'web_view') and self.web_view:
                # For web view, get selection using JavaScript
                def check_selection():
                    script = """
                    (function() {
                        var selection = window.getSelection();
                        var text = selection.toString();
                        if (text && text.trim().length > 0) {
                            return text;
                        }
                        return '';
                    })();
                    """
                    self.web_view.page().runJavaScript(
                        script,
                        lambda result: context_menu_wrapper(result)
                    )
                
                check_selection()
                return  # will continue in the callback
                
            elif hasattr(self, 'content_edit') and self.content_edit:
                # For QTextEdit, check cursor selection
                if hasattr(self.content_edit, 'textCursor'):
                    cursor = self.content_edit.textCursor()
                    selected_text = cursor.selectedText()
                    has_selection = bool(selected_text and selected_text.strip())
            
            # Build menu directly for non-web view contexts
            build_menu(has_selection, selected_text)
            menu.exec(self.mapToGlobal(position))
            
        except Exception as e:
            logger.exception(f"Error showing context menu: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred while showing the context menu: {str(e)}"
            )

    def _highlight_with_color(self, color):
        """Highlight the selected text with the specified color."""
        try:
            # Set the color in the dropdown to match
            for i in range(self.highlight_color_combo.count()):
                if self.highlight_color_combo.itemData(i) == color:
                    self.highlight_color_combo.setCurrentIndex(i)
                    break
                    
            # Now highlight with this color
            if hasattr(self, 'web_view') and self.web_view:
                # Apply highlight with JavaScript
                script = f"""
                (function() {{
                    var selection = window.getSelection();
                    var text = selection.toString();
                    if (text && text.trim().length > 0) {{
                        // Create highlight span
                        var sel = window.getSelection();
                        if (sel.rangeCount > 0) {{
                            var range = sel.getRangeAt(0);
                            
                            // Create highlight span
                            var highlightSpan = document.createElement('span');
                            highlightSpan.className = 'incrementum-highlight';
                            
                            // Set color based on selection
                            switch('{color}') {{
                                case 'yellow':
                                    highlightSpan.style.backgroundColor = 'rgba(255, 255, 0, 0.3)';
                                    break;
                                case 'green':
                                    highlightSpan.style.backgroundColor = 'rgba(0, 255, 0, 0.3)';
                                    break;
                                case 'blue':
                                    highlightSpan.style.backgroundColor = 'rgba(0, 191, 255, 0.3)';
                                    break;
                                case 'pink':
                                    highlightSpan.style.backgroundColor = 'rgba(255, 105, 180, 0.3)';
                                    break;
                                case 'orange':
                                    highlightSpan.style.backgroundColor = 'rgba(255, 165, 0, 0.3)';
                                    break;
                                default:
                                    highlightSpan.style.backgroundColor = 'rgba(255, 255, 0, 0.3)';
                            }}
                            
                            highlightSpan.style.borderRadius = '2px';
                            
                            try {{
                                // Apply highlight
                                range.surroundContents(highlightSpan);
                                
                                // Clear selection
                                sel.removeAllRanges();
                                
                                return text;
                            }} catch (e) {{
                                console.error('Error highlighting text:', e);
                                return '';
                            }}
                        }}
                    }}
                    return '';
                }})();
                """
                self.web_view.page().runJavaScript(
                    script,
                    lambda result: self._process_highlight_text(result, color)
                )
            elif hasattr(self, 'text_edit') and self.text_edit:
                cursor = self.text_edit.textCursor()
                if cursor.hasSelection():
                    # Apply highlighting
                    format = QTextCharFormat()
                    
                    # Set color based on selection
                    if color == 'yellow':
                        format.setBackground(QColor(255, 255, 0, 100))
                    elif color == 'green':
                        format.setBackground(QColor(0, 255, 0, 100))
                    elif color == 'blue':
                        format.setBackground(QColor(0, 191, 255, 100))
                    elif color == 'pink':
                        format.setBackground(QColor(255, 105, 180, 100))
                    elif color == 'orange':
                        format.setBackground(QColor(255, 165, 0, 100))
                    else:
                        format.setBackground(QColor(255, 255, 0, 100))
                        
                    cursor.mergeCharFormat(format)
                    self.text_edit.setTextCursor(cursor)
                    
                    # Process the highlight in the database
                    self._process_highlight_text(cursor.selectedText(), color)
                    
        except Exception as e:
            logger.exception(f"Error highlighting with color: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred while highlighting: {str(e)}"
            )

    def _extract_from_context_menu(self):
        """Extract text from context menu selection and highlight it."""
        try:
            if not self.selected_text or len(self.selected_text.strip()) < 5:
                QMessageBox.warning(
                    self, "Extract", 
                    "Please select more text to extract."
                )
                return
                
            # Create extract
            from core.knowledge_base.models import Extract
            
            extract = Extract(
                document_id=self.document_id,
                content=self.selected_text,
                created_date=datetime.utcnow(),
                priority=50  # Default priority
            )
            
            # Save extract
            self.db_session.add(extract)
            self.db_session.commit()
            
            # Emit the extract created signal
            self.extractCreated.emit(extract.id)
            
            # Get selected color
            color_name = self.highlight_color_combo.currentData()
            
            # Highlight the extracted text if in a web view
            if hasattr(self, 'web_view') and self.web_view:
                highlight_script = f"""
                (function() {{
                    if (typeof highlightExtractedText === 'function') {{
                        highlightExtractedText('{color_name}');
                        return true;
                    }}
                    return false;
                }})();
                """
                self.web_view.page().runJavaScript(highlight_script)
                
                # Also create a WebHighlight record for this extract
                from core.knowledge_base.models import WebHighlight
                
                highlight = WebHighlight(
                    document_id=self.document_id,
                    content=self.selected_text,
                    created_date=datetime.utcnow(),
                    color=color_name
                )
                
                # Save highlight
                self.db_session.add(highlight)
                self.db_session.commit()
            
            QMessageBox.information(
                self, "Extract", 
                "Extract created successfully. You can find it in the Knowledge Base."
            )
                
        except Exception as e:
            logger.exception(f"Error creating extract from context menu: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred: {str(e)}"
            )

    def _set_error_message(self, message):
        """Display an error message in the content area."""
        error_label = QLabel(message)
        error_label.setWordWrap(True)
        error_label.setStyleSheet("color: red; padding: 20px;")
        self.content_layout.addWidget(error_label)
    
    def _export_extracts(self):
        """Export all extracts for the current document."""
        try:
            if not hasattr(self, 'document_id') or not self.document_id:
                logger.warning("No document loaded")
                return
                
            from PyQt6.QtWidgets import QFileDialog
            
            # Ask for save location
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Export Extracts", "", "Text Files (*.txt);;HTML Files (*.html);;All Files (*)"
            )
            
            if not file_path:
                return
                
            # Get all extracts for this document
            from core.knowledge_base.models import Extract
            
            extracts = self.db_session.query(Extract)\
                .filter(Extract.document_id == self.document_id)\
                .order_by(Extract.created_date)\
                .all()
                
            if not extracts:
                QMessageBox.information(
                    self, "Export Extracts", 
                    "No extracts found for this document."
                )
                return
                
            # Format depends on file extension
            if file_path.lower().endswith('.html'):
                # Export as HTML
                html_content = f"""<!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <title>Extracts from {self.document.title}</title>
                    <style>
                        body {{ font-family: Arial, sans-serif; line-height: 1.6; margin: 20px; }}
                        h1 {{ color: #333; }}
                        .extract {{ border: 1px solid #ddd; padding: 10px; margin: 10px 0; }}
                        .extract-date {{ color: #666; font-size: 0.8em; }}
                    </style>
                </head>
                <body>
                    <h1>Extracts from: {self.document.title}</h1>
                """
                
                for extract in extracts:
                    created_date = extract.created_date.strftime('%Y-%m-%d %H:%M:%S')
                    html_content += f"""
                    <div class="extract">
                        <div class="extract-content">{extract.content}</div>
                        <div class="extract-date">Created: {created_date}</div>
                    </div>
                    """
                
                html_content += """
                </body>
                </html>
                """
                
                # Write to file
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                    
            else:
                # Export as plain text
                text_content = f"EXTRACTS FROM: {self.document.title}\n"
                text_content += "=" * 50 + "\n\n"
                
                for extract in extracts:
                    created_date = extract.created_date.strftime('%Y-%m-%d %H:%M:%S')
                    text_content += f"{extract.content}\n\n"
                    text_content += f"Created: {created_date}\n"
                    text_content += "-" * 40 + "\n\n"
                
                # Write to file
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(text_content)
            
            QMessageBox.information(
                self, "Export Successful", 
                f"Extracts exported to {file_path}"
            )
                
        except Exception as e:
            logger.exception(f"Error exporting extracts: {e}")
            QMessageBox.warning(
                self, "Export Error", 
                f"An error occurred while exporting extracts: {str(e)}"
            )

    def _load_audio(self):
        """Load an audio file for playback with position tracking."""
        try:
            from ui.load_audio_helper import setup_audio_player
            
            # Calculate initial position
            target_position = 0
            if hasattr(self.document, 'position') and self.document.position is not None:
                target_position = self.document.position
                
            # Set up the audio player
            self.audio_player = setup_audio_player(
                self, 
                self.document, 
                self.db_session, 
                target_position
            )
            
            # Add to layout
            self.content_layout.addWidget(self.audio_player)
            
            # Update last accessed timestamp
            self.document.last_accessed = datetime.now()
            self.db_session.commit()
            
        except Exception as e:
            logger.exception(f"Error loading audio file: {e}")
            error_label = QLabel(f"Error loading audio file: {str(e)}")
            error_label.setStyleSheet("color: red;")
            self.content_layout.addWidget(error_label)

    def _create_toolbar(self):
        """Create the document toolbar."""
        toolbar = QToolBar("Document Toolbar")
        toolbar.setIconSize(QSize(24, 24))
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        
        # Create actions for toolbar
        from PyQt6.QtGui import QIcon
        
        # Add fallback methods if they don't exist
        if not hasattr(self, '_on_save'):
            setattr(self, '_on_save', lambda: logger.warning("Save method not implemented"))
            
        if not hasattr(self, '_on_print'):
            setattr(self, '_on_print', lambda: logger.warning("Print method not implemented"))
            
        if not hasattr(self, '_on_highlight'):
            setattr(self, '_on_highlight', lambda: logger.warning("Highlight method not implemented"))
            
        if not hasattr(self, '_on_extract'):
            setattr(self, '_on_extract', lambda: logger.warning("Extract method not implemented"))
            
        if not hasattr(self, '_on_add_to_queue'):
            setattr(self, '_on_add_to_queue', lambda: logger.warning("Add to queue method not implemented"))
            
        if not hasattr(self, '_on_zoom_in'):
            setattr(self, '_on_zoom_in', lambda: logger.warning("Zoom in method not implemented"))
            
        if not hasattr(self, '_on_zoom_out'):
            setattr(self, '_on_zoom_out', lambda: logger.warning("Zoom out method not implemented"))
            
        if not hasattr(self, '_on_zoom_reset'):
            setattr(self, '_on_zoom_reset', lambda: logger.warning("Zoom reset method not implemented"))
        
        # First, make sure all the actions exist before trying to add them
        if not hasattr(self, 'save_action'):
            self.save_action = QAction(QIcon(":/icons/save.png"), "Save", self)
            self.save_action.setToolTip("Save document")
            self.save_action.triggered.connect(self._on_save)
            
        if not hasattr(self, 'print_action'):
            self.print_action = QAction(QIcon(":/icons/print.png"), "Print", self)
            self.print_action.setToolTip("Print document")
            self.print_action.triggered.connect(self._on_print)
            
        if not hasattr(self, 'highlight_action'):
            self.highlight_action = QAction(QIcon(":/icons/highlight.png"), "Highlight", self)
            self.highlight_action.setToolTip("Highlight selected text")
            self.highlight_action.triggered.connect(self._on_highlight)
            
        if not hasattr(self, 'extract_action'):
            self.extract_action = QAction(QIcon(":/icons/extract.png"), "Extract", self)
            self.extract_action.setToolTip("Extract selected text")
            self.extract_action.triggered.connect(self._on_extract)
            
        if not hasattr(self, 'add_to_queue_action'):
            self.add_to_queue_action = QAction(QIcon(":/icons/queue.png"), "Add to Queue", self)
            self.add_to_queue_action.setToolTip("Add to reading queue")
            self.add_to_queue_action.triggered.connect(self._on_add_to_queue)
            
        if not hasattr(self, 'zoom_in_action'):
            self.zoom_in_action = QAction(QIcon(":/icons/zoom_in.png"), "Zoom In", self)
            self.zoom_in_action.setToolTip("Zoom in")
            self.zoom_in_action.triggered.connect(self._on_zoom_in)
            
        if not hasattr(self, 'zoom_out_action'):
            self.zoom_out_action = QAction(QIcon(":/icons/zoom_out.png"), "Zoom Out", self)
            self.zoom_out_action.setToolTip("Zoom out")
            self.zoom_out_action.triggered.connect(self._on_zoom_out)
            
        if not hasattr(self, 'zoom_reset_action'):
            self.zoom_reset_action = QAction(QIcon(":/icons/zoom_reset.png"), "Reset Zoom", self)
            self.zoom_reset_action.setToolTip("Reset zoom")
            self.zoom_reset_action.triggered.connect(lambda: self._on_zoom_reset())
        
        # Add actions to toolbar
        toolbar.addAction(self.save_action)
        toolbar.addAction(self.print_action)
        toolbar.addSeparator()
        
        toolbar.addAction(self.highlight_action)
        toolbar.addAction(self.extract_action)
        toolbar.addSeparator()
        
        toolbar.addAction(self.add_to_queue_action)
        
        # Create read later button action if it doesn't exist
        if not hasattr(self, 'read_later_button'):
            self.read_later_button = QAction(QIcon(":/icons/read_later.png"), "Read Later", self)
            self.read_later_button.setToolTip("Add to reading queue for later review")
            if not hasattr(self, '_on_add_read_later'):
                setattr(self, '_on_add_read_later', self._on_add_to_queue)  # Use add_to_queue as fallback
            self.read_later_button.triggered.connect(self._on_add_read_later)
        
        toolbar.addAction(self.read_later_button)
        
        toolbar.addSeparator()
        
        toolbar.addAction(self.zoom_in_action)
        toolbar.addAction(self.zoom_out_action)
        toolbar.addAction(self.zoom_reset_action)
        
        return toolbar

    def _on_add_read_later(self):
        """Add the current document to the reading queue for later reading."""
        try:
            # Check if document exists
            if not self.document_id:
                QMessageBox.warning(self, "Error", "No document is currently open.")
                return
                
            # Get the document from database
            document = self.db_session.query(Document).get(self.document_id)
            if not document:
                QMessageBox.warning(self, "Error", "Document not found in database.")
                return
                
            # Schedule the document for later reading
            # Default to 3 days from now if not already scheduled
            if not document.next_reading_date:
                document.next_reading_date = datetime.now() + timedelta(days=3)
            
            # Set priority if not already set
            if not document.priority or document.priority < 50:
                document.priority = 50
                
            # Save changes
            self.db_session.add(document)
            self.db_session.commit()
            
            # Show confirmation
            QMessageBox.information(
                self, "Added to Queue", 
                f"Document '{document.title}' has been added to the reading queue."
            )
            
            # Emit signal to update queue
            if hasattr(self, 'documentQueued'):
                self.documentQueued.emit(self.document_id)
                
        except Exception as e:
            logger.exception(f"Error adding document to reading queue: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred while adding to reading queue: {str(e)}"
            )
            # Rollback in case of error
            self.db_session.rollback()

    def _on_add_to_queue(self):
        """Add the current document to the reading queue."""
        try:
            # Check if document exists
            if not self.document_id:
                QMessageBox.warning(self, "Error", "No document is currently open.")
                return
                
            # Get the document from database
            document = self.db_session.query(Document).get(self.document_id)
            if not document:
                QMessageBox.warning(self, "Error", "Document not found in database.")
                return
                
            # Set priority if not already set
            if not document.priority:
                document.priority = 50  # Default priority
                
            # Save changes
            self.db_session.add(document)
            self.db_session.commit()
            
            # Show confirmation
            QMessageBox.information(
                self, "Added to Queue", 
                f"Document '{document.title}' has been added to the reading queue."
            )
            
            # Emit signal to update queue
            if hasattr(self, 'documentQueued'):
                self.documentQueued.emit(self.document_id)
                
        except Exception as e:
            logger.exception(f"Error adding document to queue: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred while adding to queue: {str(e)}"
            )
            # Rollback in case of error
            self.db_session.rollback()

    def _on_previous(self):
        """Navigate to the previous document."""
        self.navigate.emit("previous")
    
    def _on_next(self):
        """Navigate to the next document."""
        self.navigate.emit("next")

    def _on_zoom_in(self):
        """Zoom in on the document content."""
        if hasattr(self, 'content_edit'):
            if isinstance(self.content_edit, QWebEngineView):
                # For web view, use zoom factor
                current_zoom = self.content_edit.zoomFactor()
                self.content_edit.setZoomFactor(current_zoom * 1.2)
            elif hasattr(self.content_edit, 'zoomIn'):
                # For text edit, use zoom in method
                self.content_edit.zoomIn(2)
    
    def _on_zoom_out(self):
        """Zoom out on the document content."""
        if hasattr(self, 'content_edit'):
            if isinstance(self.content_edit, QWebEngineView):
                # For web view, use zoom factor
                current_zoom = self.content_edit.zoomFactor()
                self.content_edit.setZoomFactor(current_zoom / 1.2)
            elif hasattr(self.content_edit, 'zoomOut'):
                # For text edit, use zoom out method
                self.content_edit.zoomOut(2)

    def _on_zoom_reset(self):
        """Reset zoom level to default."""
        if hasattr(self, 'content_edit'):
            if isinstance(self.content_edit, QWebEngineView):
                # For web view, set zoom factor to 1.0 (default)
                self.content_edit.setZoomFactor(1.0)
            elif hasattr(self.content_edit, 'setFont'):
                # For text edit, reset to default font size
                font = self.content_edit.font()
                font.setPointSize(10)  # Default size
                self.content_edit.setFont(font)
                
    def _on_add_to_incremental_reading(self):
        """Add the current document to the incremental reading queue."""
        try:
            if not hasattr(self, 'document_id') or not self.document_id:
                logger.warning("No document loaded")
                return
                
            # Use the IR manager to add document to queue
            ir_manager = IncrementalReadingManager(self.db_session)
            ir_manager.add_document_to_queue(self.document_id)
            
            QMessageBox.information(
                self, "Incremental Reading", 
                "Document added to incremental reading queue."
            )
                
        except Exception as e:
            logger.exception(f"Error adding to incremental reading: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred: {str(e)}"
            )
    
    def _on_highlight(self):
        """Highlight the selected text in the document."""
        try:
            if not hasattr(self, 'document_id') or not self.document_id:
                logger.warning("No document loaded")
                return
                
            # Get the selected highlight color
            color_name = self.highlight_color_combo.currentData()
            
            # Get selected text
            if hasattr(self, 'web_view') and self.web_view:
                # For web view, use JavaScript to get selected text and apply highlight
                script = f"""
                (function() {{
                    var selection = window.getSelection();
                    var text = selection.toString();
                    if (text && text.trim().length > 0) {{
                        // Apply highlight
                        if (typeof highlightExtractedText === 'function') {{
                            // Create highlight span
                            var sel = window.getSelection();
                            if (sel.rangeCount > 0) {{
                                var range = sel.getRangeAt(0);
                                
                                // Create highlight span
                                var highlightSpan = document.createElement('span');
                                highlightSpan.className = 'incrementum-highlight';
                                
                                // Set color based on selection
                                switch('{color_name}') {{
                                    case 'yellow':
                                        highlightSpan.style.backgroundColor = 'rgba(255, 255, 0, 0.3)';
                                        break;
                                    case 'green':
                                        highlightSpan.style.backgroundColor = 'rgba(0, 255, 0, 0.3)';
                                        break;
                                    case 'blue':
                                        highlightSpan.style.backgroundColor = 'rgba(0, 191, 255, 0.3)';
                                        break;
                                    case 'pink':
                                        highlightSpan.style.backgroundColor = 'rgba(255, 105, 180, 0.3)';
                                        break;
                                    case 'orange':
                                        highlightSpan.style.backgroundColor = 'rgba(255, 165, 0, 0.3)';
                                        break;
                                    default:
                                        highlightSpan.style.backgroundColor = 'rgba(255, 255, 0, 0.3)';
                                }}
                                
                                highlightSpan.style.borderRadius = '2px';
                                
                                try {{
                                    // Apply highlight
                                    range.surroundContents(highlightSpan);
                                    
                                    // Clear selection
                                    sel.removeAllRanges();
                                }} catch (e) {{
                                    console.error('Error highlighting text:', e);
                                }}
                            }}
                        }}
                        return text;
                    }}
                    return '';
                }})();
                """
                self.web_view.page().runJavaScript(
                    script,
                    lambda result: self._process_highlight_text(result, color_name)
                )
                return
            elif hasattr(self, 'text_edit') and self.text_edit:
                # For text edit, get selection and apply highlight
                cursor = self.text_edit.textCursor()
                selected_text = cursor.selectedText()
                if selected_text:
                    # Apply highlighting to the selection
                    format = QTextCharFormat()
                    
                    # Set color based on selection
                    if color_name == 'yellow':
                        format.setBackground(QColor(255, 255, 0, 100))
                    elif color_name == 'green':
                        format.setBackground(QColor(0, 255, 0, 100))
                    elif color_name == 'blue':
                        format.setBackground(QColor(0, 191, 255, 100))
                    elif color_name == 'pink':
                        format.setBackground(QColor(255, 105, 180, 100))
                    elif color_name == 'orange':
                        format.setBackground(QColor(255, 165, 0, 100))
                    else:
                        format.setBackground(QColor(255, 255, 0, 100))
                        
                    cursor.mergeCharFormat(format)
                    self.text_edit.setTextCursor(cursor)
                    self._process_highlight_text(selected_text, color_name)
                else:
                    QMessageBox.warning(
                        self, "Highlight", 
                        "Please select some text to highlight."
                    )
                    
        except Exception as e:
            logger.exception(f"Error creating highlight: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred: {str(e)}"
            )
    
    def _process_highlight_text(self, selected_text, color_name='yellow'):
        """Process text after highlighting from web view or text edit."""
        try:
            if not selected_text or len(selected_text.strip()) < 5:
                QMessageBox.warning(
                    self, "Highlight", 
                    "Please select more text to highlight (at least 5 characters)."
                )
                return
                
            # Create web highlight record
            from core.knowledge_base.models import WebHighlight
            
            highlight = WebHighlight(
                document_id=self.document_id,
                content=selected_text,
                created_date=datetime.utcnow(),
                color=color_name
            )
            
            # Save highlight
            self.db_session.add(highlight)
            self.db_session.commit()
            
            QMessageBox.information(
                self, "Highlight", 
                f"Text highlighted successfully with {color_name} color."
            )
                
        except Exception as e:
            logger.exception(f"Error creating highlight: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred: {str(e)}"
            )

    def _on_mark_reading_progress(self):
        """Mark the reading progress for the current document."""
        try:
            if not hasattr(self, 'document_id') or not self.document_id:
                logger.warning("No document loaded")
                return
                
            document = self.db_session.query(Document).get(self.document_id)
            if not document:
                logger.warning(f"Document not found: {self.document_id}")
                return
            
            # Get current position
            if hasattr(self, 'web_view') and self.web_view:
                # For web view, get scroll position using JavaScript
                self.web_view.page().runJavaScript(
                    "window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;",
                    lambda result: self._save_position_to_document(result)
                )
                return  # We'll continue in the callback
            elif hasattr(self, 'content_edit') and hasattr(self.content_edit, 'verticalScrollBar'):
                # For text edit or other scrollable widgets
                scrollbar = self.content_edit.verticalScrollBar()
                position = scrollbar.value()
                self._save_position_to_document(position)
            else:
                QMessageBox.warning(
                    self, "Reading Progress", 
                    "Unable to determine reading position for this document type."
                )
                
        except Exception as e:
            logger.exception(f"Error marking reading progress: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred: {str(e)}"
            )
    
    def _save_position_to_document(self, position):
        """Save the position to the document."""
        try:
            document = self.db_session.query(Document).get(self.document_id)
            if document:
                # Update document position directly
                document.position = position
                document.last_accessed = datetime.utcnow()
                self.db_session.commit()
                
                QMessageBox.information(
                    self, "Reading Progress", 
                    "Reading position saved. You can continue from this point next time."
                )
                
                logger.debug(f"Saved position {position} for document {self.document_id}")
            else:
                logger.warning(f"Document not found: {self.document_id}")
                QMessageBox.warning(
                    self, "Reading Progress", 
                    "Document not found. Unable to save position."
                )
        except Exception as e:
            logger.exception(f"Error saving reading position: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred: {str(e)}"
            )

    def _on_extract_selected(self, extract_id):
        """Handle when an extract is selected in the extract view.
        
        Args:
            extract_id (int): ID of the selected extract
        """
        try:
            # Get the extract from the database
            extract = self.db_session.query(Extract).get(extract_id)
            
            if not extract:
                logger.warning(f"Extract not found: {extract_id}")
                return
                
            # Highlight the extract text in the document if possible
            if hasattr(self, 'web_view') and self.web_view:
                # For web view, find and highlight the text
                script = f"""
                (function() {{
                    const text = {json.dumps(extract.content)};
                    if (!text) return false;
                    
                    const selection = window.getSelection();
                    const range = document.createRange();
                    const allTextNodes = [];
                    
                    // Get all text nodes
                    function getTextNodes(node) {{
                        if (node.nodeType === 3) {{
                            allTextNodes.push(node);
                        }} else {{
                            for (let i = 0; i < node.childNodes.length; i++) {{
                                getTextNodes(node.childNodes[i]);
                            }}
                        }}
                    }}
                    
                    getTextNodes(document.body);
                    
                    // Find the text in the document
                    for (let i = 0; i < allTextNodes.length; i++) {{
                        const nodeText = allTextNodes[i].textContent;
                        const index = nodeText.indexOf(text);
                        if (index >= 0) {{
                            // Found the text
                            range.setStart(allTextNodes[i], index);
                            range.setEnd(allTextNodes[i], index + text.length);
                            selection.removeAllRanges();
                            selection.addRange(range);
                            
                            // Scroll to the text
                            const rect = range.getBoundingClientRect();
                            window.scrollTo({{
                                top: window.scrollY + rect.top - 100,
                                behavior: 'smooth'
                            }});
                            
                            return true;
                        }}
                    }}
                    
                    return false;
                }})();
                """
                self.web_view.page().runJavaScript(script)
            elif hasattr(self, 'content_edit') and isinstance(self.content_edit, QTextEdit):
                # For text edit, find and highlight the text
                cursor = self.content_edit.textCursor()
                cursor.setPosition(0)
                self.content_edit.setTextCursor(cursor)
                
                if self.content_edit.find(extract.content):
                    # Text found, it's now selected
                    # Ensure visible
                    self.content_edit.ensureCursorVisible()
                else:
                    logger.warning(f"Could not find extract text in document: {extract.content[:50]}...")
            
            logger.debug(f"Selected extract: {extract_id}")
            
        except Exception as e:
            logger.exception(f"Error selecting extract: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred while selecting the extract: {str(e)}"
            )

    def _restore_highlights(self):
        """Restore highlights for the current document."""
        if not hasattr(self, 'document_id') or not self.document_id:
            return

        try:
            # For PDFs, highlighting is handled by the PDFViewWidget
            if hasattr(self, 'content_edit') and isinstance(self.content_edit, QWidget) and 'pdf' in str(type(self.content_edit)).lower():
                # PDFViewWidget has its own highlight loading
                return
                
            # For web content
            if hasattr(self, 'web_view') and self.web_view:
                # Get highlights from database
                highlights = self.db_session.query(WebHighlight).filter(WebHighlight.document_id == self.document_id).all()
                
                if not highlights:
                    logger.debug(f"No highlights found for document {self.document_id}")
                    return
                    
                logger.info(f"Restoring {len(highlights)} highlights for document {self.document_id}")
                
                # Build JavaScript to apply highlights
                script = """
                function applyHighlights() {
                    if (typeof registerHighlightFunctions !== 'function') {
                        console.error('Highlighting functions not available');
                        return;
                    }
                    
                    registerHighlightFunctions();
                    
                    const highlights = %s;
                    highlights.forEach(h => {
                        highlightText(h.text, h.color || 'yellow');
                    });
                }
                
                // Run when document is fully loaded
                if (document.readyState === 'complete') {
                    applyHighlights();
                } else {
                    window.addEventListener('load', applyHighlights);
                }
                """ % json.dumps([{"text": h.content, "color": h.color} for h in highlights])
                
                # Apply highlights
                self.web_view.page().runJavaScript(script)
                
            # For text content in QTextEdit
            elif hasattr(self, 'content_edit') and hasattr(self.content_edit, 'textCursor'):
                cursor = self.content_edit.textCursor()
                
                # Get highlights from database (using Highlight model for non-web documents)
                highlights = self.db_session.query(WebHighlight).filter(WebHighlight.document_id == self.document_id).all()
                
                if not highlights:
                    logger.debug(f"No highlights found for document {self.document_id}")
                    return
                    
                logger.info(f"Restoring {len(highlights)} highlights for document {self.document_id}")
                
                # Prepare text format for highlighting
                text_format = QTextCharFormat()
                
                doc = self.content_edit.document()
                
                for highlight in highlights:
                    try:
                        # Set color based on highlight color field
                        if highlight.color == 'yellow':
                            text_format.setBackground(QColor(255, 255, 0, 80))  # Yellow with transparency
                        elif highlight.color == 'green':
                            text_format.setBackground(QColor(0, 255, 0, 80))    # Green with transparency
                        elif highlight.color == 'blue':
                            text_format.setBackground(QColor(0, 255, 255, 80))  # Blue with transparency
                        elif highlight.color == 'pink':
                            text_format.setBackground(QColor(255, 192, 203, 80)) # Pink with transparency
                        elif highlight.color == 'orange':
                            text_format.setBackground(QColor(255, 165, 0, 80))   # Orange with transparency
                        else:
                            text_format.setBackground(QColor(255, 255, 0, 80))  # Default yellow
                            
                        # Find and highlight all occurrences of the text
                        text_to_highlight = highlight.content
                        
                        # Start from the beginning
                        cursor.setPosition(0)
                        
                        # Find and highlight all occurrences
                        while cursor.position() < doc.characterCount():
                            cursor = doc.find(text_to_highlight, cursor.position())
                            if cursor.position() == -1:
                                break
                                
                            cursor.mergeCharFormat(text_format)
                            
                    except Exception as e:
                        logger.warning(f"Error applying highlight for '{highlight.content[:20]}...': {e}")
                        
        except Exception as e:
            logger.exception(f"Error restoring highlights: {e}")
    
    def _highlight_with_color(self, color):
        """Highlight selected text with specified color."""
        try:
            if not hasattr(self, 'document_id') or not self.document_id:
                logger.warning("No document loaded, can't highlight")
                return
                
            # For PDFs, we need to handle highlighting in the PDF view
            if hasattr(self, 'content_edit') and isinstance(self.content_edit, QWidget) and 'pdf' in str(type(self.content_edit)).lower():
                if hasattr(self.content_edit, '_on_highlight_with_color'):
                    self.content_edit._on_highlight_with_color(color)
                return
                
            # Get selected text
            selected_text = ""
            
            # For web view
            if hasattr(self, 'web_view') and self.web_view:
                # Execute JavaScript to get selected text and apply highlight
                script = f"""
                (function() {{
                    const selection = window.getSelection();
                    if (!selection || selection.rangeCount === 0 || selection.toString().trim() === '') {{
                        return {{'success': false, 'error': 'No text selected'}};
                    }}
                    
                    const text = selection.toString();
                    
                    // Call highlight function if available
                    if (typeof highlightText === 'function') {{
                        highlightText(text, '{color}');
                        return {{'success': true, 'text': text}};
                    }} else {{
                        return {{'success': false, 'error': 'Highlight function not available'}};
                    }}
                }})();
                """
                
                self.web_view.page().runJavaScript(script, self._handle_highlight_result_web)
                return
                
            # For text content
            elif hasattr(self, 'content_edit') and hasattr(self.content_edit, 'textCursor'):
                cursor = self.content_edit.textCursor()
                if not cursor.hasSelection():
                    logger.warning("No text selected for highlighting")
                    return
                    
                selected_text = cursor.selectedText()
                
                # Create highlight format
                highlight_format = QTextCharFormat()
                
                # Set color based on parameter
                if color == 'yellow':
                    highlight_format.setBackground(QColor(255, 255, 0, 80))  # Yellow with transparency
                elif color == 'green':
                    highlight_format.setBackground(QColor(0, 255, 0, 80))    # Green with transparency
                elif color == 'blue':
                    highlight_format.setBackground(QColor(0, 255, 255, 80))  # Blue with transparency
                elif color == 'pink':
                    highlight_format.setBackground(QColor(255, 192, 203, 80)) # Pink with transparency
                elif color == 'orange':
                    highlight_format.setBackground(QColor(255, 165, 0, 80))   # Orange with transparency
                else:
                    highlight_format.setBackground(QColor(255, 255, 0, 80))  # Default yellow
                
                # Apply highlight
                cursor.mergeCharFormat(highlight_format)
                
                # Save highlight to database
                self._process_highlight_text(selected_text, color)
            
        except Exception as e:
            logger.exception(f"Error highlighting with color {color}: {e}")
    
    def _handle_highlight_result_web(self, result):
        """Handle result from JavaScript highlight operation."""
        try:
            if isinstance(result, dict) and result.get('success'):
                selected_text = result.get('text', '')
                if selected_text:
                    self._process_highlight_text(selected_text, result.get('color', 'yellow'))
                    logger.info(f"Highlighted text: '{selected_text[:30]}...'")
            else:
                error = result.get('error', 'Unknown error') if isinstance(result, dict) else 'Invalid result'
                logger.warning(f"Highlight failed: {error}")
        except Exception as e:
            logger.exception(f"Error processing highlight result: {e}")
    
    def _process_highlight_text(self, selected_text, color_name='yellow'):
        """Process highlighted text and save to database."""
        try:
            if not selected_text or not hasattr(self, 'document_id') or not self.document_id:
                return False
                
            if not color_name:
                color_name = 'yellow'
                
            # Create new highlight
            if hasattr(self, 'web_view') and self.web_view:
                # Web highlights use WebHighlight model
                highlight = WebHighlight(
                    document_id=self.document_id,
                    content=selected_text,
                    color=color_name,
                    created_date=datetime.utcnow()
                )
            else:
                # Other documents use Highlight model
                highlight = WebHighlight(
                    document_id=self.document_id,
                    content=selected_text,
                    color=color_name,
                    created_date=datetime.utcnow()
                )
                
            # Add to database
            self.db_session.add(highlight)
            self.db_session.commit()
            
            logger.info(f"Created highlight {highlight.id} with color {color_name}")
            return True
            
        except Exception as e:
            logger.exception(f"Error processing highlight: {e}")
            return False

    def load_document(self, document_id):
        """Load a document for viewing.
        
        Args:
            document_id (int): ID of the document to load.
            
        Returns:
            bool: True if the document was loaded successfully
        """
        try:
            # Keep any existing references alive
            if hasattr(self, 'webview'):
                self.keep_alive(self.webview)
            if hasattr(self, 'youtube_callback'):
                self.keep_alive(self.youtube_callback)
            if hasattr(self, 'audio_player'):
                self.keep_alive(self.audio_player)
                
            # Clear the document area
            self._clear_content_layout()
            
            # Get the document
            self.document_id = document_id
            self.document = self.db_session.query(Document).filter_by(id=document_id).first()
            
            if not self.document:
                raise ValueError(f"Document not found: {document_id}")
            
            # Update extracts view
            if hasattr(self, 'extract_view') and self.extract_view:
                self.extract_view.load_extracts_for_document(document_id)
            
            # Load the document content based on its type
            doc_type = self.document.content_type.lower() if hasattr(self.document, 'content_type') and self.document.content_type else "text"
            
            logger.debug(f"Loading document: {self.document.title} (Type: {doc_type})")
            
            # Handle different document types
            if doc_type == "youtube":
                self._load_youtube()
            elif doc_type == "epub":
                self._load_epub(self.db_session, self.document)
            elif doc_type == "pdf":
                self._load_pdf()
            elif doc_type == "html" or doc_type == "htm":
                self._load_html()
            elif doc_type == "txt":
                self._load_text()
            elif doc_type in ["mp3", "wav", "ogg", "flac", "m4a", "aac"]:
                self._load_audio()
            else:
                # Default to text view
                self._load_text()
            
            # Set window title to document title
            if hasattr(self, 'setWindowTitle') and callable(self.setWindowTitle):
                self.setWindowTitle(self.document.title)
                
            # After loading document successfully, start auto-save timer
            self._init_auto_save_timer()
            
            # Restore reading position if available
            self._restore_position()
            
            return True
        except Exception as e:
            logger.exception(f"Error loading document {document_id}: {e}")
            
            # Show error in view
            error_widget = QLabel(f"Error loading document: {str(e)}")
            error_widget.setWordWrap(True)
            error_widget.setStyleSheet("color: red; padding: 20px;")
            
            self._clear_content_layout()
            if hasattr(self, 'content_layout'):
                self.content_layout.addWidget(error_widget)
                
            return False
    
    def keep_alive(self, obj):
        """Keep a reference to an object to prevent garbage collection."""
        if not hasattr(self, '_kept_references'):
            self._kept_references = []
        self._kept_references.append(obj)
        
    def _load_text(self):
        """Load and display a text document."""
        try:
            # Load text from file
            file_path = self.document.file_path
            
            # Create text edit
            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            
            # Try to detect and use correct encoding
            encodings = ['utf-8', 'latin-1', 'cp1252']
            content = None
            
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            
            if content is None:
                # Last resort - try binary mode and decode with errors ignored
                with open(file_path, 'rb') as f:
                    content = f.read().decode('utf-8', errors='replace')
            
            # Set text content
            text_edit.setText(content)
            
            # Store content for later use
            self.content_text = content
            
            # Add to layout
            self.content_layout.addWidget(text_edit)
            
            # Store content edit for later use
            self.content_edit = text_edit
            
            # Restore position if available
            self._restore_position()
            
            logger.info(f"Loaded text document: {file_path}")
            return True
            
        except Exception as e:
            logger.exception(f"Error loading text: {e}")
            error_widget = QLabel(f"Error loading text: {str(e)}")
            error_widget.setWordWrap(True)
            error_widget.setStyleSheet("color: red; padding: 20px;")
            self.content_layout.addWidget(error_widget)
            return False
            
    def _load_html(self):
        """Load and display an HTML document."""
        try:
            # Load HTML from file
            file_path = self.document.file_path
            
            # Create webview if available, otherwise fall back to text view
            if HAS_WEBENGINE:
                # Read file content
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    html_content = f.read()
                
                # Create web view
                from PyQt6.QtCore import QUrl
                
                # Create web view with HTML content
                webview = self._create_webview_and_setup(html_content, QUrl.fromLocalFile(os.path.dirname(file_path)))
                
                # Add to layout
                self.content_layout.addWidget(webview)
                
                # Store references
                self.web_view = webview
                self.content_edit = webview
                
                # Store content text for later use
                import re
                # Simple text extraction from HTML
                self.content_text = re.sub(r'<[^>]+>', ' ', html_content)
                
                logger.info(f"Loaded HTML document with WebEngine: {file_path}")
                return True
                
            else:
                # Fall back to text view if web engine not available
                logger.warning("WebEngine not available, falling back to text view for HTML")
                return self._load_text()
                
        except Exception as e:
            logger.exception(f"Error loading HTML: {e}")
            error_widget = QLabel(f"Error loading HTML: {str(e)}")
            error_widget.setWordWrap(True)
            error_widget.setStyleSheet("color: red; padding: 20px;")
            self.content_layout.addWidget(error_widget)
            return False
    
    def _load_pdf(self):
        """Load and display a PDF document."""
        try:
            file_path = self.document.file_path
            
            # Check if file exists
            if not os.path.isfile(file_path):
                logger.error(f"PDF file not found: {file_path}")
                raise FileNotFoundError(f"PDF file not found: {file_path}")
            
            # First try using PyMuPDF for advanced features
            try:
                import fitz  # PyMuPDF
                
                # Custom PDF viewer using PyMuPDF
                from ui.pdf_view import PDFViewWidget
                
                # Create the PDF view widget
                pdf_widget = PDFViewWidget(self.document, self.db_session)
                
                # Connect extract created signal if available
                if hasattr(self, 'extractCreated') and hasattr(pdf_widget, 'extractCreated'):
                    pdf_widget.extractCreated.connect(self.extractCreated.emit)
                
                # Add to layout
                self.content_layout.addWidget(pdf_widget)
                
                # Store content edit for later use
                self.content_edit = pdf_widget
                
                logger.info(f"Loaded PDF with PyMuPDF: {file_path}")
                return True
                
            except (ImportError, Exception) as e:
                logger.warning(f"Could not use PyMuPDF for PDF: {str(e)}. Falling back to QPdfView.")
                # Fall back to QPdfView
                pass
                
            # Fallback: Use QPdfView from Qt
            try:
                from PyQt6.QtPdf import QPdfDocument
                from PyQt6.QtPdfWidgets import QPdfView
                
                # Create PDF view
                pdf_view = QPdfView()
                
                # Create PDF document
                pdf_document = QPdfDocument()
                
                # Load the PDF file
                pdf_document.load(file_path)
                
                # Set the document to the view
                pdf_view.setDocument(pdf_document)
                
                # Add to layout
                self.content_layout.addWidget(pdf_view)
                
                # Store content edit for later use (position tracking)
                self.content_edit = pdf_view
                
                # Extract text content for context
                # This would require a PDF text extraction library
                self.content_text = "PDF content"
                
                # Restore reading position if available
                self._restore_position()
                
                logger.info(f"Loaded PDF with QPdfView: {file_path}")
                return True
            except ImportError:
                logger.error("PDF viewing requires PyQt6.QtPdf and PyQt6.QtPdfWidgets")
                raise ImportError("PDF viewing requires additional modules that are not installed.")
                
        except Exception as e:
            logger.exception(f"Error loading PDF: {e}")
            error_widget = QLabel(f"Error loading PDF: {str(e)}")
            error_widget.setWordWrap(True)
            error_widget.setStyleSheet("color: red; padding: 20px;")
            self.content_layout.addWidget(error_widget)
            return False
    
    def _load_epub(self, db_session, document):
        """Load document in EPUB format."""
        try:
            if not HAS_WEBENGINE:
                raise Exception("Web engine not available for EPUB viewing.")
            
            # Create the web view
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtCore import QUrl
            
            content_edit = QWebEngineView()
            
            # Load the EPUB into the handler
            try:
                from core.document_processor.handlers.epub_handler import EPUBHandler
                
                # Load the file data and prepare it for the webview
                epub_handler = EPUBHandler()
                content_results = epub_handler.extract_content(document.file_path)
                html_content = content_results['html']
                
                # Process the HTML content
                html_content = self._inject_javascript_libraries(html_content)
                
                # Set up the web channel for JavaScript communication
                if not hasattr(self, 'web_channel'):
                    from PyQt6.QtWebChannel import QWebChannel
                    self.web_channel = QWebChannel()
                
                # Set the EPUB content to the web view
                content_edit.setHtml(html_content, QUrl.fromLocalFile(document.file_path))
                
                # Store the web view for later use (important for context menu)
                self.web_view = content_edit
                
                # Create callback handler
                class SelectionHandler(QObject):
                    @pyqtSlot(str)
                    def selectionChanged(self, text):
                        self.parent().selected_text = text
                        if hasattr(self.parent(), 'extract_button'):
                            self.parent().extract_button.setEnabled(bool(text and len(text.strip()) > 0))
                
                # Add the handler to the page
                handler = SelectionHandler(self)
                content_edit.page().setWebChannel(self.web_channel)
                self.web_channel.registerObject("selectionHandler", handler)
                
                # Create a method to check for selection
                def check_selection():
                    content_edit.page().runJavaScript(
                        """
                        (function() {
                            var selection = window.getSelection();
                            var text = selection.toString();
                            return text || window.text_selection || '';
                        })();
                        """,
                        self._handle_webview_selection
                    )
                
                # Store the method for later use
                content_edit.check_selection = check_selection
                
                # Connect context menu
                def context_menu_wrapper(pos):
                    # Check for selection first
                    check_selection()
                    # Process events to ensure we get the selection
                    QApplication.processEvents()
                    # Small delay to ensure selection is processed
                    QTimer.singleShot(50, lambda: self._on_content_menu(pos))
                
                # Set up context menu
                content_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                content_edit.customContextMenuRequested.connect(context_menu_wrapper)
                
                # Add position tracking
                content_edit.loadFinished.connect(lambda ok: self._inject_position_tracking_js(content_edit))
                
                # Add it to our layout
                self.content_layout.addWidget(content_edit)
                
                # Store content for later use
                self.content_edit = content_edit
                self.content_text = content_results.get('text', '')
                
                # Start auto-save timer
                self._init_auto_save_timer()
                
                # Restore position
                self._restore_position()
                
                return True
                
            except Exception as e:
                logger.exception(f"Error loading EPUB content: {e}")
                error_widget = QLabel(f"Error loading EPUB: {str(e)}")
                error_widget.setWordWrap(True)
                error_widget.setStyleSheet("color: red; padding: 20px;")
                self.content_layout.addWidget(error_widget)
                return False
                
        except Exception as e:
            logger.exception(f"Error setting up EPUB viewer: {e}")
            error_widget = QLabel(f"Error setting up EPUB viewer: {str(e)}")
            error_widget.setWordWrap(True)
            error_widget.setStyleSheet("color: red; padding: 20px;")
            self.content_layout.addWidget(error_widget)
            return False
    
    def _load_youtube(self):
        """Load and display a YouTube video document."""
        try:
            if not HAS_WEBENGINE:
                raise Exception("WebEngine not available. YouTube viewing requires PyQt6 WebEngine.")
            
            # Extract video ID from document content or URL
            from .load_youtube_helper import setup_youtube_webview, extract_video_id_from_document, WebViewCallback
            
            video_id = extract_video_id_from_document(self.document)
            
            if not video_id:
                raise ValueError("Could not extract YouTube video ID from document")
            
            # Create a QWebEngineView for embedding YouTube
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            web_view = QWebEngineView()
            web_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            
            # Create a callback handler for communication with the player
            self.youtube_callback = WebViewCallback(self)
            
            # Configure the YouTube player with our load_youtube_helper
            # Get the target position from the document if available
            target_position = getattr(self.document, 'position', 0)
            
            # Use the proper setup_youtube_webview function with all required parameters
            success, callback = setup_youtube_webview(
                web_view, 
                self.document, 
                video_id, 
                target_position=target_position,
                db_session=self.db_session
            )
            
            if not success:
                raise ValueError(f"Failed to set up YouTube player for video ID: {video_id}")
                
            # Store the enhanced callback
            self.youtube_enhanced_callback = callback
            
            # Add to layout
            self.content_layout.addWidget(web_view)
            
            # Store references
            self.web_view = web_view
            self.content_edit = web_view
            
            # Make web_view focusable to receive keyboard events
            web_view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            
            # Add event filter to handle key presses for navigation
            web_view.installEventFilter(self)
            
            # Add transcript view if available
            try:
                # Create a transcript view widget
                from ui.youtube_transcript_view import YouTubeTranscriptView
                transcript_view = YouTubeTranscriptView(video_id, self.db_session)
                transcript_view.setMaximumHeight(200)  # Limit height
                
                # Connect transcript navigation signals if available
                if hasattr(transcript_view, 'seekToTime'):
                    transcript_view.seekToTime.connect(
                        lambda time_sec: web_view.page().runJavaScript(
                            f"if(typeof player !== 'undefined' && player) {{ player.seekTo({time_sec}, true); }}"
                        )
                    )
                
                # Add to layout below the video
                self.content_layout.addWidget(transcript_view)
                
                # Store reference
                self.transcript_view = transcript_view
                
            except Exception as e:
                logger.warning(f"Could not load YouTube transcript: {e}")
                # Continue without transcript
            
            logger.info(f"Loaded YouTube video: {video_id}")
            return True
            
        except Exception as e:
            logger.exception(f"Error loading YouTube video: {e}")
            error_widget = QLabel(f"Error loading YouTube video: {str(e)}")
            error_widget.setWordWrap(True)
            error_widget.setStyleSheet("color: red; padding: 20px;")
            self.content_layout.addWidget(error_widget)
            return False
    
    def _inject_javascript_libraries(self, html_content):
        """Inject common JavaScript libraries into HTML content based on content needs."""
        
        # Check if the document already has a head tag
        has_head = "<head>" in html_content
        has_body = "<body>" in html_content
        
        # Library CDN URLs
        libraries = {
            'markdown': "https://cdn.jsdelivr.net/npm/marked/marked.min.js",
            'mermaid': "https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js",
            'plotly': "https://cdn.plot.ly/plotly-latest.min.js",
            'katex': "https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/katex.min.js",
            'katex-css': "https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/katex.min.css",
            'katex-autorender': "https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/contrib/auto-render.min.js",
            'three': "https://cdn.jsdelivr.net/npm/three@0.157.0/build/three.min.js"
        }
        
        # Determine which libraries to inject based on content
        to_inject = []
        
        # Check for library markers in content
        if "```mermaid" in html_content or "mermaid" in html_content:
            to_inject.append('mermaid')
        
        if "```math" in html_content or "\\(" in html_content or "\\[" in html_content or "$" in html_content or "math" in html_content.lower():
            to_inject.append('katex')
            to_inject.append('katex-css')
            to_inject.append('katex-autorender')
        
        if "```plotly" in html_content or "Plotly" in html_content:
            to_inject.append('plotly')
        
        if "```markdown" in html_content or "marked" in html_content or "markdown" in html_content.lower():
            to_inject.append('markdown')
        
        if "three.js" in html_content or "THREE." in html_content:
            to_inject.append('three')
        
        # Return original content if no libraries needed or if we can't find insertion points
        if not to_inject or (not has_head and not has_body):
            return html_content
        
        # Build script tags
        scripts = ""
        styles = ""
        
        for lib in to_inject:
            if lib.endswith('-css'):
                styles += f'<link rel="stylesheet" href="{libraries[lib]}">\n'
            else:
                scripts += f'<script src="{libraries[lib]}"></script>\n'
        
        # Add initialization script
        init_script = """
<script>
function initializeCustomLibraries() {
    // Initialize mermaid if available
    if (typeof mermaid !== 'undefined') {
        try {
            mermaid.initialize({
                startOnLoad: true,
                theme: 'neutral'
            });
        } catch (e) {
            console.error('Mermaid init error:', e);
        }
    }
    
    // Initialize KaTeX if available
    if (typeof katex !== 'undefined') {
        console.log('KaTeX detected, initializing...');
        
        // First approach: Find specific elements with class names
        document.querySelectorAll('.math, .katex').forEach(element => {
            try {
                // Get the raw text and trim whitespace
                let texContent = element.textContent.trim();
                console.log('Processing KaTeX element:', texContent.substring(0, 30) + '...');
                
                // Create a new element to render into (to avoid modifying the original)
                let renderElement = document.createElement('div');
                renderElement.className = 'katex-output';
                element.innerHTML = ''; // Clear the original content
                element.appendChild(renderElement);
                
                // Render the KaTeX
                katex.render(texContent, renderElement, {
                    throwOnError: false,
                    displayMode: element.classList.contains('display')
                });
            } catch (e) {
                console.error('KaTeX rendering error:', e);
                element.innerHTML = '<span style="color:red">KaTeX Error: ' + e.message + '</span><br>' + element.textContent;
            }
        });
        
        // Render inline math
        document.querySelectorAll('.math-inline').forEach(element => {
            try {
                let texContent = element.textContent.trim();
                katex.render(texContent, element, {
                    throwOnError: false,
                    displayMode: false
                });
            } catch (e) {
                console.error('KaTeX inline error:', e);
                element.innerHTML = '<span style="color:red">Error</span>';
            }
        });
        
        // Second approach: Use the auto-render extension if available
        if (typeof renderMathInElement !== 'undefined') {
            console.log('Using KaTeX auto-render extension');
            try {
                // Automatically render math in the entire document
                renderMathInElement(document.body, {
                    delimiters: [
                        {left: "$$", right: "$$", display: true},
                        {left: "$", right: "$", display: false},
                        {left: "\\(", right: "\\)", display: false},
                        {left: "\\[", right: "\\]", display: true}
                    ],
                    throwOnError: false
                });
            } catch (e) {
                console.error('KaTeX auto-render error:', e);
            }
        }
    }
    
    // Initialize markdown if available
    if (typeof marked !== 'undefined') {
        console.log('Marked.js detected, initializing...');
        
        // Set up marked options for better rendering
        marked.setOptions({
            gfm: true,          // Enable GitHub flavored markdown
            breaks: true,       // Convert line breaks to <br>
            smartLists: true,   // Use smart list behavior
            smartypants: true,  // Use smart punctuation
            xhtml: true         // Return XHTML compliant output
        });
        
        document.querySelectorAll('.markdown').forEach(element => {
            try {
                // Get the raw text
                let mdContent = element.textContent.trim();
                console.log('Processing Markdown element:', mdContent.substring(0, 30) + '...');
                
                // Parse markdown
                let htmlContent = marked.parse(mdContent);
                
                // Create a wrapper to maintain any styling
                let wrapper = document.createElement('div');
                wrapper.className = 'markdown-output';
                wrapper.innerHTML = htmlContent;
                
                // Replace content
                element.innerHTML = '';
                element.appendChild(wrapper);
            } catch (e) {
                console.error('Markdown error:', e);
                element.innerHTML = '<div class="error">Markdown rendering error: ' + e.message + '</div>';
            }
        });
    }
    
    console.log('Custom libraries initialization complete');
}

// Execute after DOM is fully loaded
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM loaded, initializing custom libraries');
    setTimeout(initializeCustomLibraries, 100);
});

// Add a button to manually trigger initialization if automatic doesn't work
window.addEventListener('load', function() {
    // Check if any library-specific elements exist but haven't been processed
    let needsInit = (
        (document.querySelector('.markdown') && !document.querySelector('.markdown-output')) ||
        (document.querySelector('.math, .katex') && !document.querySelector('.katex-output'))
    );
    
    if (needsInit) {
        console.log('Library elements found that need initialization');
        
        // Create a button to manually trigger initialization
        let btn = document.createElement('button');
        btn.textContent = 'Initialize Custom Content';
        btn.style.position = 'fixed';
        btn.style.bottom = '10px';
        btn.style.right = '10px';
        btn.style.zIndex = '9999';
        btn.style.padding = '8px 16px';
        btn.style.backgroundColor = '#0066cc';
        btn.style.color = 'white';
        btn.style.border = 'none';
        btn.style.borderRadius = '4px';
        btn.style.cursor = 'pointer';
        
        btn.onclick = function() {
            initializeCustomLibraries();
            btn.textContent = 'Initialization Complete';
            setTimeout(function() { 
                btn.style.display = 'none'; 
            }, 2000);
        };
        
        document.body.appendChild(btn);
        
        // Try one more time automatically
        setTimeout(initializeCustomLibraries, 1000);
    }
});
</script>
"""
        
        # Inject into HTML
        if has_head:
            # Insert before the closing head tag
            html_content = html_content.replace("</head>", styles + scripts + init_script + "</head>")
        elif has_body:
            # Insert after the opening body tag
            html_content = html_content.replace("<body>", "<body>\n" + styles + scripts + init_script)
        else:
            # Wrap the entire content
            html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Document</title>
    {styles}
    {scripts}
    {init_script}
</head>
<body>
    {html_content}
</body>
</html>
"""
        
        return html_content

    def eventFilter(self, watched, event):
        """Filter events to handle key presses in the web view."""
        if (watched == self.web_view or watched == self.content_edit) and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            
            # Handle N/P keys for navigation
            if key == Qt.Key.Key_N:
                self._on_next()
                return True
            elif key == Qt.Key.Key_P:
                self._on_previous()
                return True
                
        # Let default handler process the event
        return super().eventFilter(watched, event)

