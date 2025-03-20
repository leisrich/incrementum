# If the patching approach doesn't work, here's a complete replacement for document_view.py
# Save this as ui/document_view.py.new and rename it if needed

import os
import logging
from typing import Optional, List, Dict
from datetime import datetime
import json

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QScrollArea, QSplitter, QTextEdit,
    QToolBar, QMenu, QMessageBox, QApplication, QDialog,
    QTabWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QPoint, QUrl, QObject, QTimer
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
from .load_youtube_helper import setup_youtube_webview
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
    
    def load_document(self, document_id):
        """Load and display a document."""
        try:
            # Clear previous content
            for i in reversed(range(self.content_layout.count())):
                item = self.content_layout.itemAt(i)
                if item.widget():
                    item.widget().deleteLater()
            
            # Load document from database
            self.document = self.db_session.query(Document).get(document_id)
            if not self.document:
                logger.error(f"Document not found: {document_id}")
                return
            
            # Update document last accessed time
            self.document.last_accessed = datetime.utcnow()
            self.db_session.commit()
            
            # Load document extracts
            self.extract_view.load_extracts_for_document(document_id)
            
            # Special case: check if a jina_web document is actually a YouTube video
            if self.document.content_type == 'jina_web' and hasattr(self.document, 'source_url'):
                source_url = self.document.source_url
                if source_url and ('youtube.com' in source_url or 'youtu.be' in source_url):
                    logger.info(f"Detected YouTube URL in jina_web document: {self.document.id}, updating content type")
                    self.document.content_type = 'youtube'
                    self.db_session.commit()
            
            # Display based on content type
            if self.document.content_type == 'pdf':
                self._load_pdf()
            elif self.document.content_type == 'epub':
                self._load_epub()
            elif self.document.content_type == 'txt':
                self._load_text()
            elif self.document.content_type == 'html' or self.document.content_type == 'htm':
                self._load_html()
            elif self.document.content_type == 'docx':
                self._load_docx()
            elif self.document.content_type == 'youtube':
                self._load_youtube()
            elif self.document.content_type == 'jina_web':
                # Try to load as HTML for jina_web documents
                self._load_html()
            else:
                # Unsupported format
                label = QLabel(f"Unsupported document type: {self.document.content_type}")
                self.content_layout.addWidget(label)
                logger.warning(f"Unsupported document type: {self.document.content_type}")
            
            # Remember document ID
            self.document_id = document_id
            
        except Exception as e:
            logger.exception(f"Error loading document: {e}")
            label = QLabel(f"Error loading document: {str(e)}")
            self.content_layout.addWidget(label)
    
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
            # Read HTML file
            with open(self.document.file_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            # Parse with BeautifulSoup to extract text
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            self.content_text = soup.get_text()
            
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
            
    def _load_youtube(self):
        """Load and display a YouTube video."""
        try:
            if not HAS_WEBENGINE:
                raise ImportError("YouTube videos require QWebEngineView which is not available")
            
            if not self.document.file_path or not os.path.isfile(self.document.file_path):
                raise FileNotFoundError(f"YouTube metadata file not found: {self.document.file_path}")

            # Read metadata from file
            with open(self.document.file_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            video_id = metadata.get('video_id')
            if not video_id:
                raise ValueError("No video ID found in metadata")

            # Set window title
            title = metadata.get('title', 'YouTube Video')
            
            # Create the web view for the YouTube player
            self.web_view = QWebEngineView()
            
            # Configure settings
            self.web_view.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            self.web_view.settings().setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
            self.web_view.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
            
            # Create a splitter to hold both the video and transcript
            self.content_splitter = QSplitter(Qt.Orientation.Vertical)
            
            # Add web view (YouTube player) to the splitter
            self.content_splitter.addWidget(self.web_view)
            
            # Add to layout
            self.content_layout.addWidget(self.content_splitter)
            
            # Load HTML for YouTube player
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body {{ margin: 0; padding: 0; overflow: hidden; }}
                    #player {{ width: 100%; height: 100vh; }}
                </style>
            </head>
            <body>
                <div id="player"></div>
                
                <script>
                    // YouTube API
                    var tag = document.createElement('script');
                    tag.src = "https://www.youtube.com/iframe_api";
                    var firstScriptTag = document.getElementsByTagName('script')[0];
                    firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);
                    
                    var player;
                    function onYouTubeIframeAPIReady() {{
                        player = new YT.Player('player', {{
                            videoId: '{video_id}',
                            playerVars: {{
                                'autoplay': 0,
                                'rel': 0,
                                'cc_load_policy': 1,
                                'modestbranding': 1
                            }},
                            events: {{
                                'onReady': onPlayerReady,
                                'onStateChange': onPlayerStateChange
                            }}
                        }});
                    }}
                    
                    function onPlayerReady(event) {{
                        console.log('Player ready');
                    }}
                    
                    function onPlayerStateChange(event) {{
                        console.log('Player state changed');
                        // 0=ended, 1=playing, 2=paused, 3=buffering, 5=video cued
                        if (event.data === 0) {{
                            console.log('Video ended');
                        }}
                    }}

                    // Function to get player state
                    function getPlayerState() {{
                        if (typeof player !== 'undefined' && player) {{
                            return {{
                                currentTime: player.getCurrentTime(),
                                playerState: player.getPlayerState()
                            }};
                        }}
                        return null;
                    }}
                </script>
            </body>
            </html>
            """
            
            # Load the HTML content
            self.web_view.setHtml(html_content, QUrl(f"https://www.youtube.com/watch?v={video_id}"))
            
            # Check for transcript in metadata
            if 'transcript' in metadata and metadata['transcript']:
                # Create transcript view
                self.transcript_view = YouTubeTranscriptView(
                    self.db_session,
                    document_id=self.document_id,
                    metadata_file=self.document.file_path
                )
                
                # Connect extract created signal
                self.transcript_view.extractCreated.connect(self.extractCreated)
                
                # Add to splitter
                self.content_splitter.addWidget(self.transcript_view)
                
                # Set size ratios (60% video, 40% transcript)
                self.content_splitter.setSizes([600, 400])
                
                logger.info(f"Loaded YouTube video with transcript: {video_id}")
            else:
                logger.info(f"Loaded YouTube video without transcript: {video_id}, metadata keys: {list(metadata.keys())}")
                
                # Create a label explaining that no transcript is available
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
                
                # Create a button to reimport the video with transcript
                reimport_container = QWidget()
                reimport_layout = QVBoxLayout(reimport_container)
                
                reimport_button = QPushButton("Reimport Video with Transcript")
                reimport_button.clicked.connect(self._on_reimport_youtube)
                reimport_layout.addWidget(reimport_button)
                reimport_layout.addWidget(no_transcript_label)
                
                # Add to splitter
                self.content_splitter.addWidget(reimport_container)
            
            # Save original source URL if available
            self.source_url = metadata.get('source_url', '')
            
            # Add a callback to handle JavaScript messages
            self.youtube_callback = None
            
            # Setup position tracking if supported
            if hasattr(setup_youtube_webview, '__call__'):
                try:
                    logger.debug(f"Setting up YouTube position tracking for {self.document_id}")
                    self.youtube_callback = setup_youtube_webview(
                        self.web_view,
                        self.document_id,
                        self.db_session
                    )
                except Exception as e:
                    logger.exception(f"Error setting up YouTube position tracking: {e}")
            
        except Exception as e:
            logger.exception(f"Error loading YouTube video: {e}")
            error_widget = QLabel(f"Error loading YouTube video: {str(e)}")
            error_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            error_widget.setWordWrap(True)
            error_widget.setStyleSheet("color: red; padding: 20px;")
            self.content_layout.addWidget(error_widget)
    
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
        """Handle close event to save document position."""
        self._save_position()
        self._save_view_state()
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
        """Reimport the current YouTube video to try getting transcript."""
        if not hasattr(self, 'document') or not self.document:
            return
        
        try:
            # Get the source URL
            source_url = self.document.source_url
            if not source_url:
                QMessageBox.warning(
                    self, "Reimport Error", 
                    "Cannot reimport video: No source URL available."
                )
                return
            
            # Show a message about what's happening
            QMessageBox.information(
                self, "Reimporting Video", 
                "The video will be reimported to attempt to get a transcript. "
                "This may take a moment. The page will reload when complete."
            )
            
            # Use the YouTube handler to reimport
            from core.document_processor.handlers.youtube_handler import YouTubeHandler
            
            # Create a new handler instance
            youtube_handler = YouTubeHandler()
            
            # Download from URL and get metadata
            file_path, metadata = youtube_handler.download_from_url(source_url)
            
            if not file_path:
                QMessageBox.warning(
                    self, "Reimport Error", 
                    "Failed to reimport the video. Please try again later."
                )
                return
            
            # Check if transcript was found
            if 'transcript' not in metadata or not metadata['transcript']:
                QMessageBox.warning(
                    self, "No Transcript Available", 
                    "No transcript could be found for this video.\n\n"
                    "Possible reasons:\n"
                    "• Transcripts are disabled by the video creator\n"
                    "• The video does not have any captions\n"
                    "• The video is age-restricted or private\n\n"
                    "Try a different video or manually create extracts."
                )
                return
            
            # Update the document with the new file path
            self.document.file_path = file_path
            self.db_session.commit()
            
            # Reload the document
            self.load_document(self.document_id)
            
            QMessageBox.information(
                self, "Success", 
                "The video has been reimported successfully with its transcript."
            )
            
        except Exception as e:
            logger.exception(f"Error reimporting YouTube video: {e}")
            QMessageBox.warning(
                self, "Reimport Error", 
                f"Failed to reimport the video: {str(e)}"
            )

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
