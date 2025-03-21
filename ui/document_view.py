# If the patching approach doesn't work, here's a complete replacement for document_view.py
# Save this as ui/document_view.py.new and rename it if needed

import os
import logging
from typing import Optional, List, Dict
from datetime import datetime
import json
import time
import tempfile
from io import BytesIO
from pathlib import Path
import base64

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QScrollArea, QSplitter, QTextEdit,
    QToolBar, QMenu, QMessageBox, QApplication, QDialog,
    QTabWidget, QLineEdit
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QPoint, QUrl, QObject, QTimer, QPointF, QSize, QByteArray
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEngineSettings
    from PyQt6.QtWebChannel import QWebChannel
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False
from PyQt6.QtGui import QAction, QTextCursor, QColor, QTextCharFormat

from core.knowledge_base.models import Document, Extract
from core.content_extractor.extractor import ContentExtractor
from .document_extracts_view import DocumentExtractsView
from .load_epub_helper import setup_epub_webview
from .load_youtube_helper import setup_youtube_webview, extract_video_id_from_document
from .youtube_transcript_view import YouTubeTranscriptView

logger = logging.getLogger(__name__)

class WebViewCallback(QObject):
    """Class to handle callbacks from JavaScript in QWebEngineView."""
    
    def __init__(self, document_view):
        super().__init__()
        self.document_view = document_view
    
    @pyqtSlot(str)
    def selectionChanged(self, text):
        """Handle selection change from JavaScript."""
        self.document_view._handle_webview_selection(text)

class DocumentView(QWidget):
    """UI component for viewing and processing documents."""
    
    extractCreated = pyqtSignal(int)  # extract_id
    
    def __init__(self, db_session, document_id=None):
        super().__init__()
        
        self.db_session = db_session
        self.document_id = document_id
        self.document = None
        self.selected_text = ""
        self.content_text = ""
        self.youtube_callback = None
        
        # View state tracking
        self.view_state = {
            "zoom_factor": 1.0,
            "position": None,
            "size": None,
            "scroll_position": 0
        }
        
        # Create the UI
        self._create_ui()
        
        # Load document if provided
        if document_id:
            self.load_document(document_id)
    
    def _create_ui(self):
        """Create the UI components."""
        # Main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Toolbar
        toolbar = QToolBar()
        
        # Document navigation actions
        self.prev_action = QAction("Previous", self)
        self.prev_action.triggered.connect(self._on_previous)
        toolbar.addAction(self.prev_action)
        
        self.next_action = QAction("Next", self)
        self.next_action.triggered.connect(self._on_next)
        toolbar.addAction(self.next_action)
        
        toolbar.addSeparator()
        
        # Extract actions
        self.create_extract_action = QAction("Create Extract", self)
        self.create_extract_action.triggered.connect(self._on_create_extract)
        toolbar.addAction(self.create_extract_action)
        
        layout.addWidget(toolbar)
        
        # Content splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Document content area
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        
        # Content will be added dynamically based on document type
        
        splitter.addWidget(self.content_widget)
        
        # Extracts area
        self.extract_view = DocumentExtractsView(self.db_session)
        self.extract_view.extractSelected.connect(self._on_extract_selected)
        splitter.addWidget(self.extract_view)
        
        # Set initial sizes
        splitter.setSizes([700, 300])
        
        layout.addWidget(splitter)
        
        self.setLayout(layout)
    
    def _create_webview_and_setup(self, html_content, base_url):
        """Create a QWebEngineView and set it up with the content."""
        if not HAS_WEBENGINE:
            logger.warning("QWebEngineView not available, falling back to QTextEdit")
            editor = QTextEdit()
            editor.setReadOnly(True)
            editor.setHtml(html_content)
            return editor
        
        # Create WebEngine view for HTML content
        webview = QWebEngineView()
        
        # Configure settings to allow all JavaScript functionality
        settings = webview.settings()
        settings.setAttribute(settings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(settings.WebAttribute.JavascriptCanAccessClipboard, True)
        settings.setAttribute(settings.WebAttribute.JavascriptCanOpenWindows, True)
        settings.setAttribute(settings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(settings.WebAttribute.AllowRunningInsecureContent, True)
        settings.setAttribute(settings.WebAttribute.PluginsEnabled, True)
        
        # Create a channel for JavaScript communication
        channel = QWebChannel(webview.page())
        
        # Create callback handler
        callback_handler = WebViewCallback(self)
        channel.registerObject("callbackHandler", callback_handler)
        
        # Set the channel to the page
        webview.page().setWebChannel(channel)
        
        # Check if we need to inject JavaScript libraries
        injected_html = self._inject_javascript_libraries(html_content)
        
        # Load content with proper base URL for resources
        if base_url:
            webview.setHtml(injected_html, base_url)
        else:
            webview.setHtml(injected_html)
        
        # Inject JavaScript to capture selections - using a cleaner approach
        selection_js = """
        // Wait for document to be fully loaded
        document.addEventListener('DOMContentLoaded', function() {
            // Add selection change listener
            document.addEventListener('selectionchange', function() {
                const selection = window.getSelection();
                const text = selection.toString();
                // Only send non-empty selections
                if (text && text.trim().length > 0) {
                    // Check if callback handler is available
                    if (typeof window.callbackHandler !== 'undefined') {
                        window.callbackHandler.selectionChanged(text);
                    } else {
                        console.error('Callback handler not available');
                    }
                }
            });

            // Track scroll position changes
            document.addEventListener('scroll', function() {
                // Throttle scroll events to reduce overhead
                if (window.scrollTrackTimeout) {
                    clearTimeout(window.scrollTrackTimeout);
                }
                window.scrollTrackTimeout = setTimeout(function() {
                    const scrollPosition = window.pageYOffset || document.documentElement.scrollTop;
                    if (typeof window.callbackHandler !== 'undefined') {
                        // Store position in a window variable so we can access it later
                        window.lastScrollPosition = scrollPosition;
                    }
                }, 200); // 200ms throttle
            });
            
            // Initialize any custom libraries
            if (typeof initializeCustomLibraries === 'function') {
                try {
                    initializeCustomLibraries();
                    console.log('Custom libraries initialized');
                } catch (e) {
                    console.error('Error initializing custom libraries:', e);
                }
            }
        });
        """
        
        # Simple direct selection capture script as fallback
        simple_selection_js = """
        document.onselectionchange = function() {
            var selection = window.getSelection();
            var text = selection.toString();
            if (text && text.trim().length > 0) {
                window.text_selection = text; // Store in a global variable
            }
        };
        """
        
        # Inject the simple selection script immediately
        webview.page().runJavaScript(simple_selection_js)
        
        # Inject the main script after the page has loaded
        webview.loadFinished.connect(lambda ok: webview.page().runJavaScript(selection_js))
        
        # Add a method to manually get the current selection
        def check_selection():
            webview.page().runJavaScript(
                "window.getSelection().toString() || window.text_selection || '';",
                self._handle_webview_selection
            )
        
        # Store the method to check selection
        webview.check_selection = check_selection
        
        # Connect mouse release to check selection
        webview.mouseReleaseEvent = lambda event: (
            super(QWebEngineView, webview).mouseReleaseEvent(event),
            check_selection()
        )
        
        # Connect context menu request to check selection before showing menu
        webview.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        
        # Store the original handler
        original_handler = self._on_content_menu
        
        # Create a wrapper that first checks selection
        def context_menu_wrapper(pos):
            check_selection()
            # Call the original handler after a small delay
            QApplication.processEvents()
            original_handler(pos)
        
        webview.customContextMenuRequested.connect(context_menu_wrapper)
        
        return webview
    
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
    
    def keep_alive(self, obj):
        """Keep a reference to an object to prevent garbage collection."""
        if not hasattr(self, '_kept_references'):
            self._kept_references = []
        self._kept_references.append(obj)
        
    def load_document(self, document_id):
        """Load a document for viewing.
        
        Args:
            document_id (int): ID of the document to load.
        """
        try:
            # Keep any existing references alive
            if hasattr(self, 'webview'):
                self.keep_alive(self.webview)
            if hasattr(self, 'youtube_callback'):
                self.keep_alive(self.youtube_callback)
                
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
                self._load_epub()
            elif doc_type == "pdf":
                self._load_pdf()
            elif doc_type == "html" or doc_type == "htm":
                self._load_html()
            elif doc_type == "txt":
                self._load_text()
            else:
                # Default to text view
                self._load_text()
            
            # Set window title to document title
            if hasattr(self, 'setWindowTitle') and callable(self.setWindowTitle):
                self.setWindowTitle(self.document.title)
                
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
    
    def _load_pdf(self):
        """Load and display a PDF document."""
        try:
            file_path = self.document.file_path
            
            # Check if file exists
            if not os.path.isfile(file_path):
                logger.error(f"PDF file not found: {file_path}")
                
                # Try alternative file path if in temporary directory
                if '/tmp/' in file_path:
                    tmp_dir = os.path.dirname(file_path)
                    if os.path.exists(tmp_dir):
                        files = os.listdir(tmp_dir)
                        pdf_files = [f for f in files if f.endswith('.pdf')]
                        if pdf_files:
                            new_path = os.path.join(tmp_dir, pdf_files[0])
                            logger.info(f"Using alternative PDF file found in the same directory: {new_path}")
                            file_path = new_path
                            
                            # Update the document's file_path
                            self.document.file_path = file_path
                            self.db_session.commit()
                        else:
                            logger.error(f"No PDF files found in {tmp_dir}")
                            raise FileNotFoundError(f"PDF file not found: {file_path}")
                    else:
                        logger.error(f"Temporary directory not found: {tmp_dir}")
                        raise FileNotFoundError(f"PDF file not found: {file_path}")
                else:
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
                return
                
            except (ImportError, Exception) as e:
                logger.warning(f"Could not use PyMuPDF for PDF: {str(e)}. Falling back to QPdfView.")
                # Fall back to QPdfView
                pass
                
            # Fallback: Use QPdfView from Qt
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
            
        except ImportError:
            logger.error("PDF viewing requires PyQt6.QtPdf and PyQt6.QtPdfWidgets")
            label = QLabel("PDF viewing requires additional modules that are not installed.")
            self.content_layout.addWidget(label)
        except Exception as e:
            logger.exception(f"Error loading PDF: {e}")
            label = QLabel(f"Error loading PDF: {str(e)}")
            self.content_layout.addWidget(label)

    def _load_epub(self):
        """Load and display an EPUB document."""
        try:
            if not HAS_WEBENGINE:
                raise ImportError("EPUB viewing requires QWebEngineView")
            
            # Create a web view for the EPUB content
            webview = QWebEngineView()
            
            # Load the EPUB as HTML (using a specialized EPUB handler)
            from core.document_processor.handlers.epub_handler import EPUBHandler
            epub_handler = EPUBHandler()
            
            # IMPORTANT: Fixed the AttributeError: 'EPUBHandler' object has no attribute 'extract_html_content'
            # by using extract_content() method which returns a dict with 'html' key instead
            content_results = epub_handler.extract_content(self.document.file_path)
            html_content = content_results['html']
            
            # Check for JavaScript libraries that might be needed
            libs_to_check = ['mermaid', 'katex', 'plotly', 'markdown', 'three.js']
            detected_libs = []
            
            for lib in libs_to_check:
                if lib in html_content.lower():
                    detected_libs.append(lib)
                    
            if detected_libs:
                logger.info(f"Detected potential JavaScript libraries in EPUB: {', '.join(detected_libs)}")
                # Process HTML content to add libraries
                html_content = self._inject_javascript_libraries(html_content)
            
            # Set base URL for resources
            base_url = QUrl.fromLocalFile(os.path.dirname(self.document.file_path) + os.path.sep)
            
            # Set content to web view with proper base path
            webview.setHtml(html_content, base_url)
            
            # Set up EPUB-specific tracking
            setup_epub_webview(self.document, webview, self.db_session)
            
            # Add to layout
            self.content_layout.addWidget(webview)
            
            # Store for later use
            self.content_edit = webview
            self.web_view = webview  # Keep reference for _save_position
            self.content_text = content_results['text']
        
        except ImportError as e:
            logger.error(f"EPUB viewing requires QWebEngineView: {e}")
            label = QLabel("EPUB viewing requires QWebEngineView which is not available.")
            self.content_layout.addWidget(label)
        except Exception as e:
            logger.exception(f"Error loading EPUB: {e}")
            label = QLabel(f"Error loading EPUB: {str(e)}")
            self.content_layout.addWidget(label)
    
    def _load_text(self):
        """Load and display a text document."""
        try:
            # Create text edit
            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            
            # Read file content
            with open(self.document.file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Set content
            text_edit.setPlainText(content)
            
            # Add to layout
            self.content_layout.addWidget(text_edit)
            
            # Store for later use
            self.content_edit = text_edit
            self.content_text = content
            
            # Restore position
            self._restore_position()
            
        except Exception as e:
            logger.exception(f"Error loading text document: {e}")
            label = QLabel(f"Error loading text document: {str(e)}")
            self.content_layout.addWidget(label)
    
    def _load_html(self):
        """Load and display an HTML document."""
        try:
            # Log file info
            logger.info(f"Loading HTML document from {self.document.file_path}")
            file_size = os.path.getsize(self.document.file_path) if os.path.exists(self.document.file_path) else 0
            logger.info(f"HTML file size: {file_size} bytes")
            
            # Check if file exists and is not empty
            if not os.path.exists(self.document.file_path):
                logger.error(f"HTML file does not exist: {self.document.file_path}")
                label = QLabel(f"HTML file not found: {os.path.basename(self.document.file_path)}")
                self.content_layout.addWidget(label)
                return
                
            if file_size == 0:
                logger.error(f"HTML file is empty: {self.document.file_path}")
                label = QLabel("The HTML file is empty. No content to display.")
                self.content_layout.addWidget(label)
                return
            
            # Read HTML file
            try:
                with open(self.document.file_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()
            except UnicodeDecodeError:
                # Try with a different encoding if UTF-8 fails
                logger.warning(f"UTF-8 decoding failed, trying with ISO-8859-1")
                with open(self.document.file_path, 'r', encoding='ISO-8859-1') as f:
                    html_content = f.read()
                    
            # Log content preview for debugging
            content_preview = html_content[:200] + "..." if len(html_content) > 200 else html_content
            logger.debug(f"HTML content preview: {content_preview}")
            
            if not html_content.strip():
                logger.error("HTML content is empty after reading")
                label = QLabel("The HTML file contains no content.")
                self.content_layout.addWidget(label)
                return
            
            # Parse with BeautifulSoup to extract text
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Check if there's any meaningful content
            body_content = soup.body.get_text().strip() if soup.body else ""
            self.content_text = soup.get_text()
            
            if not body_content:
                logger.warning("HTML document contains no visible text content")
                
                # Try to display the raw HTML instead
                text_edit = QTextEdit()
                text_edit.setReadOnly(True)
                text_edit.setPlainText(html_content)
                self.content_layout.addWidget(text_edit)
                self.content_edit = text_edit
                logger.info("Displaying raw HTML content instead")
                return
            
            # Set up base URL for loading resources
            base_url = QUrl.fromLocalFile(os.path.dirname(self.document.file_path) + os.path.sep)
            
            # Log which JavaScript libraries might be needed
            libs_to_check = ['mermaid', 'katex', 'plotly', 'markdown', 'three.js']
            detected_libs = []
            
            for lib in libs_to_check:
                if lib in html_content.lower():
                    detected_libs.append(lib)
                    
            if detected_libs:
                logger.info(f"Detected potential JavaScript libraries in HTML: {', '.join(detected_libs)}")
            
            # Create web view with libraries injected as needed
            webview = self._create_webview_and_setup(html_content, base_url)
            
            # Add to layout
            self.content_layout.addWidget(webview)
            
            # Store for later use
            self.content_edit = webview
            self.web_view = webview  # Keep reference for _save_position
            
            # Set up position tracking similar to EPUB
            setup_epub_webview(self.document, webview, self.db_session)
            
            logger.info("HTML document loaded successfully")
            
        except Exception as e:
            logger.exception(f"Error loading HTML document: {e}")
            label = QLabel(f"Error loading HTML document: {str(e)}")
            self.content_layout.addWidget(label)
    
    def _load_docx(self):
        """Load and display a DOCX document."""
        try:
            # Use python-docx to extract text
            import docx
            
            doc = docx.Document(self.document.file_path)
            content = "\n".join([paragraph.text for paragraph in doc.paragraphs])
            
            # Create text edit
            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            text_edit.setPlainText(content)
            
            # Add to layout
            self.content_layout.addWidget(text_edit)
            
            # Store for later use
            self.content_edit = text_edit
            self.content_text = content
            
            # Restore position
            self._restore_position()
            
        except ImportError:
            logger.error("DOCX viewing requires python-docx library")
            label = QLabel("DOCX viewing requires additional libraries that are not installed.")
            self.content_layout.addWidget(label)
        except Exception as e:
            logger.exception(f"Error loading DOCX document: {e}")
            label = QLabel(f"Error loading DOCX document: {str(e)}")
            self.content_layout.addWidget(label)

    def _update_youtube_position(self):
        """Update and save the current YouTube position."""
        if not hasattr(self, 'web_view') or not self.web_view:
            return
            
        # Use JavaScript to get the current position
        self.web_view.page().runJavaScript(
            "getCurrentPosition();",
            self._handle_position_update
        )
        
    def _handle_position_update(self, position):
        """Handle position update from JavaScript."""
        if position is None or not isinstance(position, (int, float)):
            return
            
        # Update position label
        if hasattr(self, 'position_label'):
            self.position_label.setText(f"Position: {int(position)}s")
        
        # Update the document position in the database
        if hasattr(self, 'document') and self.document:
            try:
                if position > 0:  # Don't save if at the beginning
                    self.document.position = int(position)
                    self.db_session.commit()
                    logger.debug(f"Saved YouTube position: {position}")
            except Exception as e:
                logger.error(f"Error saving YouTube position: {e}")
                
    def _on_save_youtube_position(self):
        """Manually save the current YouTube position."""
        if hasattr(self, 'youtube_callback') and self.youtube_callback:
            try:
                self.youtube_callback.savePosition()
                if hasattr(self, 'youtube_status'):
                    self.youtube_status.setText(f"Position saved: {self.youtube_callback.current_position}s")
            except Exception as e:
                logger.error(f"Error manually saving position: {e}")
        else:
            self._update_youtube_position()  # Fallback
        
    def _on_seek_youtube_position(self):
        """Handle seeking to a specific position in a YouTube video."""
        if not hasattr(self, 'web_view') or not self.web_view or not hasattr(self, 'seek_time_input'):
            return
            
        try:
            # Get position from input
            time_text = self.seek_time_input.text()
            position = int(time_text)
            
            # Use JavaScript to seek
            seek_script = f"seekToTime({position});"
            self.web_view.page().runJavaScript(seek_script)
            
            # Update backend
            if hasattr(self, 'youtube_callback') and self.youtube_callback:
                self.youtube_callback.current_position = position
                self.youtube_callback.onTimeUpdate(position)
                
            # Update label
            if hasattr(self, 'position_label'):
                self.position_label.setText(f"Position: {position}s")
                
            # Update status
            if hasattr(self, 'youtube_status'):
                self.youtube_status.setText(f"Seeking to position: {position}s")
                
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid position value: {e}")
            if hasattr(self, 'youtube_status'):
                self.youtube_status.setText(f"Invalid position: {e}")

    def _load_youtube(self):
        """Load YouTube video content."""
        try:
            # Import required widgets here to ensure they're in scope
            from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit, QSplitter, QSizePolicy
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtCore import Qt
            
            if not HAS_WEBENGINE:
                raise ImportError("YouTube videos require QWebEngineView which is not available")
                
            # Clear any existing content from the layout
            self._clear_content_layout()
            
            # Get video ID
            video_id = extract_video_id_from_document(self.document)
            
            if not video_id:
                logger.error("Could not extract YouTube video ID")
                raise ValueError("Could not extract YouTube video ID from document")
            
            # Create a splitter to hold both the video and transcript
            self.content_splitter = QSplitter(Qt.Orientation.Vertical)
            self.content_splitter.setChildrenCollapsible(False)  # Prevent sections from being fully collapsed
            
            # Create a container for the video
            video_container = QWidget()
            video_layout = QVBoxLayout(video_container)
            video_layout.setContentsMargins(0, 0, 0, 0)
            video_layout.setSpacing(5)
            
            # Create a WebView and make it expand to fill available space
            self.webview = QWebEngineView()
            self.webview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)  # Allow expansion
            video_layout.addWidget(self.webview, stretch=1)  # Add stretch to prioritize video
            
            # Get the target position (if available)
            target_position = 0
            if hasattr(self.document, 'position') and self.document.position:
                target_position = self.document.position
                
            # Add controls widget with more compact layout
            controls_widget = QWidget()
            timestamp_layout = QHBoxLayout(controls_widget)
            timestamp_layout.setContentsMargins(5, 2, 5, 2)
            timestamp_layout.setSpacing(2)
            
            # Add position label
            self.position_label = QLabel(f"Position: {target_position}s")
            timestamp_layout.addWidget(self.position_label)
            
            # Add spacer between position and seek controls
            timestamp_layout.addStretch(1)
            
            # Add seek label
            timestamp_label = QLabel("Seek to:")
            timestamp_layout.addWidget(timestamp_label)
            
            # Add input field for timestamp
            self.seek_time_input = QLineEdit()
            self.seek_time_input.setPlaceholderText("Enter time in seconds or MM:SS")
            self.seek_time_input.setText(str(target_position))
            timestamp_layout.addWidget(self.seek_time_input)
            
            # Add seek button
            seek_button = QPushButton("Seek")
            seek_button.clicked.connect(self._on_seek_youtube_position)
            timestamp_layout.addWidget(seek_button)
            
            # Add a save button for manual saving of position
            save_button = QPushButton("Save Position")
            save_button.clicked.connect(self._on_save_youtube_position)
            timestamp_layout.addWidget(save_button)
            
            # Add controls to video container (no stretch, keep it compact)
            video_layout.addWidget(controls_widget)
            
            # Add video container to the splitter
            self.content_splitter.addWidget(video_container)
            
            # Set up the webview with the YouTube player
            success, callback = setup_youtube_webview(
                self.webview, 
                self.document, 
                video_id, 
                target_position,
                self.db_session
            )
            
            if success and callback:
                # Store references for later use
                self.youtube_callback = callback
                self.web_view = self.webview
            
                
                # Check for transcript in metadata
                if hasattr(self.document, 'file_path') and self.document.file_path and os.path.exists(self.document.file_path):
                    try:
                        with open(self.document.file_path, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)
                            if 'transcript' in metadata and metadata['transcript']:
                                # Create transcript view
                                self.transcript_view = YouTubeTranscriptView(
                                    self.db_session,
                                    document_id=self.document_id,
                                    metadata_file=self.document.file_path
                                )
                                self.transcript_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
                                
                                # Connect extract created signal
                                self.transcript_view.extractCreated.connect(self.extractCreated)
                                
                                # Add to splitter
                                self.content_splitter.addWidget(self.transcript_view)
                                
                                # Set initial sizes (70% video, 30% transcript)
                                self.content_splitter.setSizes([700, 300])
                            else:
                                # No transcript, show message
                                no_transcript_widget = QWidget()
                                no_transcript_layout = QVBoxLayout(no_transcript_widget)
                                
                                no_transcript_label = QLabel(
                                    "No transcript is available for this video.\n\n"
                                    "Possible reasons:\n"
                                    "• Transcripts are disabled by the video creator\n"
                                    "• The video does not have any captions\n"
                                    "• The video is age-restricted or private\n\n"
                                    "Try reimporting or using a different video."
                                )
                                no_transcript_label.setWordWrap(True)
                                no_transcript_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                                no_transcript_label.setStyleSheet("background-color: #f0f0f0; padding: 20px; border-radius: 5px;")
                                
                                reimport_button = QPushButton("Reimport Video with Transcript")
                                reimport_button.clicked.connect(self._on_reimport_youtube)
                                
                                no_transcript_layout.addWidget(reimport_button)
                                no_transcript_layout.addWidget(no_transcript_label)
                                
                                # Add to splitter
                                self.content_splitter.addWidget(no_transcript_widget)
                    except Exception as e:
                        logger.warning(f"Could not load transcript metadata: {e}")
                
                # Add the splitter to the main layout and make it expand
                self.content_layout.addWidget(self.content_splitter, stretch=1)
                
                logger.info(f"Loaded YouTube video: {video_id}")
                return True
            else:
                error_msg = f"Failed to set up YouTube player for video {video_id}"
                self.youtube_status.setText(error_msg)
                self.youtube_status.setStyleSheet("color: red; background-color: #fee; padding: 5px; border-radius: 3px;")
                logger.error(error_msg)
                
                # Add the container to the main layout anyway to show the error
                self.content_layout.addWidget(self.content_splitter, stretch=1)
                return False
                
        except Exception as e:
            logger.exception(f"Error loading YouTube content: {e}")
            from PyQt6.QtWidgets import QLabel
            error_widget = QLabel(f"Error loading YouTube video: {str(e)}")
            error_widget.setStyleSheet("color: red; padding: 20px;")
            error_widget.setWordWrap(True)
            self.content_layout.addWidget(error_widget)
            return False
            
    def _clear_content_layout(self):
        """Clear all widgets from the content layout."""
        if hasattr(self, 'content_layout'):
            # Remove all widgets from the layout
            while self.content_layout.count():
                item = self.content_layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.setParent(None)
                    widget.deleteLater()

    def _handle_webview_selection(self, selected_text):
        """Handle text selection from web view."""
        if selected_text and selected_text.strip():
            self.selected_text = selected_text.strip()
    
    @pyqtSlot(QPoint)
    def _on_content_menu(self, pos):
        """Show context menu for document content."""
        # Create menu
        menu = QMenu(self)
        
        # Add actions
        if hasattr(self, 'selected_text') and self.selected_text:
            create_extract_action = menu.addAction("Create Extract")
            create_extract_action.triggered.connect(self._on_create_extract)
        
        # Show menu
        menu.exec(self.mapToGlobal(pos))
    
    @pyqtSlot()
    def _on_previous(self):
        """Navigate to previous page/section."""
        # Implementation depends on document type
        pass
    
    @pyqtSlot()
    def _on_next(self):
        """Navigate to next page/section."""
        # Implementation depends on document type
        pass
    
    @pyqtSlot(int)
    def _on_extract_selected(self, extract_id):
        """Handle extract selection from extract view."""
        self.extractCreated.emit(extract_id)
    
    @pyqtSlot()
    def _on_create_extract(self):
        """Create an extract from selected text."""
        if not self.selected_text:
            return
        
        # Different handling based on the type of content editor
        if HAS_WEBENGINE and isinstance(self.content_edit, QWebEngineView):
            # For QWebEngineView, we already have the selected text from _handle_webview_selection
            # We need to get context differently since we don't have textCursor
            
            # Special handling for YouTube videos
            if hasattr(self, 'document') and self.document and self.document.content_type == 'youtube':
                # For YouTube, use the content_text which should have video info
                context = self.content_text
                position = "youtube"
                if hasattr(self, 'youtube_callback') and self.youtube_callback:
                    # Include current position in the video if available
                    if hasattr(self.youtube_callback, 'current_position'):
                        position = f"youtube:{self.youtube_callback.current_position}"
            # Regular WebView (EPUB, HTML)
            elif self.content_text:
                # Try to find the selection in the content_text to get proper context
                selection_index = self.content_text.find(self.selected_text)
                if selection_index >= 0:
                    # Get surrounding context
                    start_pos = max(0, selection_index - 100)
                    end_pos = min(len(self.content_text), selection_index + len(self.selected_text) + 100)
                    context = self.content_text[start_pos:end_pos]
                    position = f"pos:{selection_index}"
                else:
                    # Fallback if we can't find the exact text
                    context = self.selected_text
                    position = "unknown"
            else:
                context = self.selected_text
                position = "unknown"
        else:
            # For QTextEdit and similar widgets, use the textCursor to get context
            cursor = self.content_edit.textCursor()
            position = cursor.position()
            
            # Try to get some context before and after selection
            start_pos = max(0, position - 100)
            end_pos = min(len(self.content_text), position + 100)
            
            context = self.content_text[start_pos:end_pos]
            position = f"pos:{position}"
        
        # Create the extract
        extract = Extract(
            content=self.selected_text,
            context=context,
            document_id=self.document_id,
            position=position,
            created_date=datetime.utcnow()
        )
        
        try:
            # Add to database
            self.db_session.add(extract)
            self.db_session.commit()
            
            # Refresh extracts view
            self.extract_view.load_extracts_for_document(self.document_id)
            
            # Emit signal
            self.extractCreated.emit(extract.id)
            
            # Clear selection
            self.selected_text = ""
            
        except Exception as e:
            logger.exception(f"Error creating extract: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Failed to create extract: {str(e)}"
            )
    
    def showEvent(self, event):
        """Handle widget show event to restore view state."""
        super().showEvent(event)
        
        # Restore view state when tab is shown again
        self._restore_view_state()
        
        # Emit signal when the document is shown
        QTimer.singleShot(100, self._on_tab_activated)
        
    def hideEvent(self, event):
        """Handle widget hide event to save view state."""
        super().hideEvent(event)
        
        # Save view state when tab is hidden
        self._save_view_state()
        
        # Emit signal when the document is hidden
        QTimer.singleShot(0, self._on_tab_deactivated)
    
    def _on_tab_activated(self):
        """Handle tab activation."""
        # Additional things to do when a tab becomes active
        # For example, update toolbar actions or refresh content
        logger.debug(f"Tab activated for document: {self.document_id}")
        
        # Special handling for different content types
        if hasattr(self, 'document') and self.document:
            # For PDF content, ensure proper restoration
            if self.document.content_type == 'pdf' and hasattr(self, 'content_edit'):
                # If it's a PDFViewWidget, call its specific methods
                if hasattr(self.content_edit, 'set_view_state') and hasattr(self.content_edit, 'get_view_state'):
                    # Any specific PDF restoration
                    pass
            
            # For YouTube content, which uses web_view instead of content_edit
            elif self.document.content_type == 'youtube' and hasattr(self, 'web_view'):
                logger.debug(f"Tab activated for YouTube video: {self.document.id}")
                # YouTube-specific restoration if needed
                pass
                    
            # For general web content, ensure JavaScript is running
            elif hasattr(self, 'content_edit') and HAS_WEBENGINE and isinstance(self.content_edit, QWebEngineView):
                # Refresh web content to ensure JavaScript is working
                refresh_script = """
                if (typeof refreshActiveContent === 'function') {
                    refreshActiveContent();
                }
                """
                self.content_edit.page().runJavaScript(refresh_script)
    
    def _on_tab_deactivated(self):
        """Handle tab deactivation."""
        # Additional things to do when a tab becomes inactive
        logger.debug(f"Tab deactivated for document: {self.document_id}")
        
        # Save any unsaved changes or state
        self._save_position()
        
        # Content type specific handling
        if hasattr(self, 'document') and self.document:
            # PDF-specific handling
            if self.document.content_type == 'pdf' and hasattr(self, 'content_edit'):
                # Additional PDF-specific state saving
                pass
            
            # YouTube-specific handling
            elif self.document.content_type == 'youtube' and hasattr(self, 'web_view'):
                # Save YouTube position if needed
                # This is usually handled automatically by the setup_youtube_webview callback
                pass
    
    def _save_view_state(self):
        """Save the current view state for later restoration."""
        try:
            # Handle YouTube specially since it uses web_view instead of content_edit
            if hasattr(self, 'document') and self.document and self.document.content_type == 'youtube':
                if hasattr(self, 'web_view') and HAS_WEBENGINE:
                    # Using JavaScript to get YouTube player state
                    self.web_view.page().runJavaScript(
                        "getPlayerState();",
                        lambda state: setattr(self, 'view_state', {**self.view_state, "youtube_state": state}) if state else None
                    )
                return
            
            # If content_edit is a PDFViewWidget, use its specific methods
            if hasattr(self, 'content_edit'):
                # Special handling for PDF view widget
                if hasattr(self.content_edit, 'get_view_state'):
                    pdf_state = self.content_edit.get_view_state()
                    self.view_state.update(pdf_state)
                    logger.debug(f"Saved PDF-specific view state: {pdf_state}")
                elif hasattr(self.content_edit, 'zoom_factor'):
                    self.view_state["zoom_factor"] = self.content_edit.zoom_factor
                
                # Save scroll position for QTextEdit and similar
                if hasattr(self.content_edit, 'verticalScrollBar'):
                    scrollbar = self.content_edit.verticalScrollBar()
                    if scrollbar:
                        self.view_state["scroll_position"] = scrollbar.value()
                        
                # Save scroll position for webviews
                if HAS_WEBENGINE and isinstance(self.content_edit, QWebEngineView):
                    # Using JavaScript to get scroll position
                    self.content_edit.page().runJavaScript(
                        "window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;",
                        lambda pos: setattr(self, 'view_state', {**self.view_state, "scroll_position": pos})
                    )
                    
            # Save size and position if needed
            self.view_state["size"] = self.size()
            
            # Store state in database if needed for persistent storage across sessions
            if hasattr(self, 'document') and self.document:
                # In a production version, you might want to store this in the database
                # import json
                # self.document.view_state = json.dumps(self.view_state)
                # self.db_session.commit()
                pass
                
            logger.debug(f"Saved view state for document {self.document_id}: {self.view_state}")
                
        except Exception as e:
            logger.exception(f"Error saving view state: {e}")
    
    def _restore_view_state(self):
        """Restore the previously saved view state."""
        try:
            if not hasattr(self, 'content_edit') or not self.content_edit:
                return
                
            # If content_edit is a PDFViewWidget, use its specific methods
            if hasattr(self.content_edit, 'set_view_state'):
                # Create a copy of the view state to avoid modifying the original
                pdf_state = {k: v for k, v in self.view_state.items() 
                            if k in ['page', 'zoom_factor', 'position']}
                
                if pdf_state:
                    self.content_edit.set_view_state(pdf_state)
                    logger.debug(f"Restored PDF-specific view state: {pdf_state}")
                return  # Exit early since PDF view handles its own state
                
            # For other view types, apply generic restoration
            
            # Restore zoom factor
            if "zoom_factor" in self.view_state and self.view_state["zoom_factor"]:
                if hasattr(self.content_edit, 'set_zoom'):
                    self.content_edit.set_zoom(self.view_state["zoom_factor"])
                
            # Restore scroll position
            if "scroll_position" in self.view_state and self.view_state["scroll_position"] is not None:
                # For QTextEdit and similar
                if hasattr(self.content_edit, 'verticalScrollBar'):
                    scrollbar = self.content_edit.verticalScrollBar()
                    if scrollbar:
                        scrollbar.setValue(self.view_state["scroll_position"])
                        
                # For web views
                if HAS_WEBENGINE and isinstance(self.content_edit, QWebEngineView):
                    pos = self.view_state["scroll_position"]
                    script = f"window.scrollTo(0, {pos});"
                    self.content_edit.page().runJavaScript(script)
                    
            # Apply sizing if needed
            if "size" in self.view_state and self.view_state["size"]:
                # Usually not needed as the tab widget will control size,
                # but could be useful in some cases
                pass
                
            logger.debug(f"Restored view state for document {self.document_id}: {self.view_state}")
                
        except Exception as e:
            logger.exception(f"Error restoring view state: {e}")
    
    def closeEvent(self, event):
        try:
            # Force save YouTube position if applicable
            if (hasattr(self, 'document') and self.document and 
                self.document.content_type == 'youtube' and 
                hasattr(self, 'youtube_callback') and self.youtube_callback):
                
                logger.info(f"Saving YouTube position on close: {self.youtube_callback.current_position}")
                self.youtube_callback.savePosition()
                
            self._save_position()
            self._save_view_state()
            self.db_session.commit()  # Ensure changes are committed
        except Exception as e:
            logger.exception(f"Error in closeEvent: {e}")
        super().closeEvent(event)
    
    def _save_position(self):
        """Save the current reading position."""
        try:
            # Check if we have a document to save position for
            if not hasattr(self, 'document') or not self.document:
                return
            
            # For QTextEdit
            if hasattr(self, 'text_view') and isinstance(self.text_view, QTextEdit):
                cursor = self.text_view.textCursor()
                position = cursor.position()
                
                # Update the document
                self.document.position = position
                self.db_session.commit()
                logger.debug(f"Saved text cursor position: {position}")
            
            # For QWebEngineView (position handled by the helper module)
            elif hasattr(self, 'web_view') and QWebEngineView and isinstance(self.web_view, QWebEngineView):
                # Position is saved automatically by the setup_youtube_webview callback system
                logger.debug("WebView position handled by helper module")
                
        except Exception as e:
            logger.exception(f"Error saving position: {e}")
    
    def _restore_position(self):
        """Restore the last reading position."""
        try:
            if not hasattr(self, 'document') or not self.document:
                return
                
            # Get stored position
            position = getattr(self.document, 'position', None)
            if position is None or position <= 0:
                logger.info(f"No stored position found for {self.document.title}")
                return
                    
            logger.info(f"Attempting to restore position {position} for {self.document.title}")
                
            # Determine how to set position based on document type and view
            if hasattr(self, 'content_edit'):
                if isinstance(self.content_edit, QTextEdit):
                    # For text documents, set cursor position
                    cursor = self.content_edit.textCursor()
                        
                    # Make sure position is within valid range
                    doc_length = len(self.content_edit.toPlainText())
                    position = min(position, doc_length)
                        
                    cursor.setPosition(position)
                    self.content_edit.setTextCursor(cursor)
                        
                    # Ensure the cursor is visible
                    self.content_edit.ensureCursorVisible()
                    logger.info(f"Restored text document position: {position}")
                        
                elif HAS_WEBENGINE and isinstance(self.content_edit, QWebEngineView):
                    # For WebEngine view (EPUB/HTML/YouTube), position is handled by the helper module
                    # No need to do anything here as it's done when the view is initialized
                    pass
                else:
                    logger.warning(f"Unknown content editor type, can't restore position: {type(self.content_edit)}")
            else:
                logger.warning("No content_edit available to restore position to")
                
        except Exception as e:
            logger.exception(f"Error restoring document position: {e}")

    def _on_reimport_youtube(self):
        """Reimport the YouTube video with transcript."""
        try:
            from PyQt6.QtWidgets import QMessageBox
            
            # Show confirmation dialog
            reply = QMessageBox.question(
                self, 
                "Reimport YouTube Video",
                "This will reimport the YouTube video and attempt to fetch the transcript again. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                # Check if we have a source URL or video ID
                if hasattr(self.document, 'source_url') and self.document.source_url:
                    source_url = self.document.source_url
                    
                    # Import the document processor in the handler to avoid circular imports
                    from core.document_processor.handlers.youtube_handler import YouTubeHandler
                    handler = YouTubeHandler()
                    
                    # Extract video ID from source URL
                    video_id = handler._extract_video_id(source_url)
                    
                    if video_id:
                        # Show importing message
                        self.youtube_status.setText(f"Reimporting video {video_id} with transcript...")
                        self.youtube_status.setStyleSheet("color: #000; background-color: #ffd; padding: 5px; border-radius: 3px;")
                        
                        # Process in a background thread to avoid UI freezing
                        from PyQt6.QtCore import QThread, pyqtSignal
                        
                        class ImportThread(QThread):
                            importFinished = pyqtSignal(bool, str)
                            
                            def __init__(self, handler, url, parent=None):
                                super().__init__(parent)
                                self.handler = handler
                                self.url = url
                                
                            def run(self):
                                try:
                                    # Reimport with force_transcript=True
                                    success = self.handler.process_url(self.url, force_transcript=True)
                                    self.importFinished.emit(success, "")
                                except Exception as e:
                                    self.importFinished.emit(False, str(e))
                        
                        # Create and start the thread
                        self.import_thread = ImportThread(handler, source_url, self)
                        self.import_thread.importFinished.connect(self._on_reimport_finished)
                        self.import_thread.start()
                    else:
                        self.youtube_status.setText("Could not extract video ID from URL")
                        self.youtube_status.setStyleSheet("color: red; background-color: #fee; padding: 5px; border-radius: 3px;")
                else:
                    self.youtube_status.setText("No source URL available for reimport")
                    self.youtube_status.setStyleSheet("color: red; background-color: #fee; padding: 5px; border-radius: 3px;")
        except Exception as e:
            logger.exception(f"Error starting YouTube reimport: {e}")
            self.youtube_status.setText(f"Error: {str(e)}")
            self.youtube_status.setStyleSheet("color: red; background-color: #fee; padding: 5px; border-radius: 3px;")
            
    def _on_reimport_finished(self, success, error_msg):
        """Handle completion of YouTube reimport."""
        if success:
            self.youtube_status.setText("Video reimported successfully. Reloading...")
            self.youtube_status.setStyleSheet("color: green; background-color: #efe; padding: 5px; border-radius: 3px;")
            
            # Reload the document after a short delay
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(1500, lambda: self.load_document(self.document_id))
        else:
            self.youtube_status.setText(f"Reimport failed: {error_msg}")
            self.youtube_status.setStyleSheet("color: red; background-color: #fee; padding: 5px; border-radius: 3px;")

    def save_document(self):
        """Save the current document state to the database."""
        try:
            if not self.document or not self.document_id:
                logger.debug("No document to save")
                return False
                
            # Save position
            self._save_position()
            
            # Save view state
            self._save_view_state()
            
            # Update last_modified timestamp
            self.document.last_modified = datetime.utcnow()
            
            # Commit changes to the database
            self.db_session.commit()
            
            logger.debug(f"Document {self.document_id} saved successfully")
            return True
            
        except Exception as e:
            logger.exception(f"Error saving document: {e}")
            return False

    # Import necessary module to avoid error
    from datetime import datetime
