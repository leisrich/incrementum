# If the patching approach doesn't work, here's a complete replacement for document_view.py
# Save this as ui/document_view.py.new and rename it if needed

import os
import logging
from typing import Optional, List, Dict
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QScrollArea, QSplitter, QTextEdit,
    QToolBar, QMenu, QMessageBox, QApplication, QDialog,
    QTabWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QPoint, QUrl, QObject, QTimer
try:
    # Import QWebEngineView if available for better HTML rendering
    from PyQt6.QtWebEngineWidgets import QWebEngineView
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
            from PyQt6.QtPdf import QPdfDocument
            from PyQt6.QtPdfWidgets import QPdfView
            
            # Create PDF view
            pdf_view = QPdfView()
            
            # Create PDF document
            pdf_document = QPdfDocument()
            
            # Load the PDF file
            pdf_document.load(self.document.file_path)
            
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
            logger.info(f"Starting to load YouTube video for document {self.document.id}")
            if not HAS_WEBENGINE:
                raise ImportError("YouTube viewing requires QWebEngineView")
            
            # Create a web view for the YouTube content
            webview = QWebEngineView()
            
            # Double-check that we have a valid source_url as a fallback
            if (not hasattr(self.document, 'file_path') or not self.document.file_path or 
                not os.path.exists(self.document.file_path)) and hasattr(self.document, 'source_url'):
                logger.warning(f"YouTube document {self.document.id} has invalid file_path, using source_url instead")
                self.document.file_path = self.document.source_url
                self.db_session.commit()
            
            # Log file path info to help diagnose
            logger.info(f"YouTube document file_path: {self.document.file_path}")
            if hasattr(self.document, 'source_url'):
                logger.info(f"YouTube document source_url: {self.document.source_url}")
            
            # Configure web view settings for better performance
            if hasattr(webview, 'settings'):
                settings = webview.settings()
                settings.setAttribute(settings.WebAttribute.JavascriptEnabled, True)
                settings.setAttribute(settings.WebAttribute.PluginsEnabled, True)
                settings.setAttribute(settings.WebAttribute.AutoLoadImages, True)
                settings.setAttribute(settings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
            
            # Setup the YouTube player with position tracking
            logger.info("Calling setup_youtube_webview")
            success, callback = setup_youtube_webview(self.document, webview, self.db_session)
            logger.info(f"setup_youtube_webview result: success={success}")
            
            if not success:
                # If direct loading failed, try to extract ID from source_url
                logger.warning("Direct setup failed, trying to recover video ID")
                if hasattr(self.document, 'source_url') and self.document.source_url:
                    from core.document_processor.handlers.youtube_handler import YouTubeHandler
                    handler = YouTubeHandler()
                    
                    # Try to get the video ID
                    video_id = handler._extract_video_id(self.document.source_url)
                    logger.info(f"Extracted video ID from source_url: {video_id}")
                    if video_id:
                        logger.info(f"Recovered YouTube video ID {video_id} from source_url for document {self.document.id}")
                        
                        # Create a temporary metadata file with the video ID
                        import json
                        import tempfile
                        
                        metadata = {
                            'video_id': video_id,
                            'title': self.document.title,
                            'author': getattr(self.document, 'author', 'Unknown'),
                            'source_url': self.document.source_url
                        }
                        
                        fd, temp_path = tempfile.mkstemp(suffix='.json')
                        with os.fdopen(fd, 'w', encoding='utf-8') as f:
                            json.dump(metadata, f, ensure_ascii=False, indent=2)
                        
                        logger.info(f"Created temporary metadata file at {temp_path}")
                        
                        # Update the document's file path
                        self.document.file_path = temp_path
                        self.db_session.commit()
                        
                        # Try to set up again with the new metadata
                        logger.info("Trying setup_youtube_webview again with new metadata")
                        success, callback = setup_youtube_webview(self.document, webview, self.db_session)
                        logger.info(f"Second setup_youtube_webview result: success={success}")
                
                # If still not successful, try a direct iframe embed as last resort
                if not success:
                    logger.warning("Setup still failed, trying direct iframe embed")
                    try:
                        # Try to extract video ID directly
                        from core.document_processor.handlers.youtube_handler import YouTubeHandler
                        handler = YouTubeHandler()
                        
                        # Try all possible sources for the video ID
                        video_id = None
                        sources = []
                        
                        if hasattr(self.document, 'source_url') and self.document.source_url:
                            sources.append(self.document.source_url)
                        
                        if hasattr(self.document, 'file_path') and self.document.file_path:
                            sources.append(self.document.file_path)
                            
                            # If it's a JSON file, try to read it
                            if os.path.exists(self.document.file_path) and self.document.file_path.endswith('.json'):
                                try:
                                    with open(self.document.file_path, 'r') as f:
                                        data = json.load(f)
                                        if 'video_id' in data:
                                            sources.append(data['video_id'])
                                except Exception as e:
                                    logger.error(f"Error reading JSON file: {e}")
                        
                        # Try each source
                        for source in sources:
                            video_id = handler._extract_video_id(source)
                            if video_id:
                                break
                        
                        if video_id:
                            logger.info(f"Found video ID {video_id} using direct extraction")
                            
                            # Create direct HTML
                            position = getattr(self.document, 'position', 0) or 0
                            html = f"""
                            <!DOCTYPE html>
                            <html>
                            <head>
                                <meta charset="utf-8">
                                <meta name="viewport" content="width=device-width, initial-scale=1">
                                <title>{self.document.title}</title>
                                <style>
                                    body {{
                                        margin: 0;
                                        padding: 0;
                                        overflow: hidden;
                                        background-color: #000;
                                    }}
                                    iframe {{
                                        width: 100%;
                                        height: 100vh;
                                        border: none;
                                    }}
                                </style>
                            </head>
                            <body>
                                <iframe 
                                    src="https://www.youtube.com/embed/{video_id}?autoplay=1&start={position}" 
                                    allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture" 
                                    allowfullscreen>
                                </iframe>
                            </body>
                            </html>
                            """
                            
                            logger.info("Loading direct iframe HTML")
                            webview.setHtml(html)
                            success = True
                        else:
                            raise ValueError("Could not determine YouTube video ID")
                    except Exception as direct_error:
                        logger.exception(f"Error with direct iframe: {direct_error}")
                        raise ValueError("Failed to set up YouTube player with any method")
            
            # Store the callback for later use
            self.youtube_callback = callback
            
            # Add to layout
            self.content_layout.addWidget(webview)
            logger.info("Added YouTube webview to layout")
            
            # Store for later use
            self.content_edit = webview
            
            # Extract video info for content text (for extracts)
            try:
                from core.document_processor.handlers.youtube_handler import YouTubeHandler
                handler = YouTubeHandler()
                self.content_text = handler.extract_content(self.document.file_path)
            except Exception as extract_error:
                logger.warning(f"Could not extract YouTube content: {extract_error}")
                self.content_text = f"YouTube video: {self.document.title}"
            
            logger.info("YouTube video loaded successfully")
            
        except ImportError as e:
            logger.error(f"YouTube viewing requires QWebEngineView: {e}")
            label = QLabel("YouTube viewing requires QWebEngineView which is not available.")
            self.content_layout.addWidget(label)
        except Exception as e:
            logger.exception(f"Error loading YouTube video: {e}")
            label = QLabel(f"Error loading YouTube video: {str(e)}")
            self.content_layout.addWidget(label)
    
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
    
    def closeEvent(self, event):
        """Handle close event to save document position."""
        self._save_position()
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

    # Import necessary module to avoid error
    from datetime import datetime
