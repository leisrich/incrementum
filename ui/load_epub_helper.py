# ui/load_epub_helper.py

import os
import logging

from PyQt6.QtCore import QUrl, QTimer
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False

logger = logging.getLogger(__name__)

def setup_epub_webview(document, content_edit, db_session, restore_position=True, theme_manager=None):
    """
    Set up appropriate handlers for tracking position in EPUB documents.
    
    Args:
        document: The Document object being displayed
        content_edit: The QWebEngineView instance
        db_session: Database session
        restore_position: Whether to restore the position
        theme_manager: ThemeManager instance for applying themes
        
    Returns:
        bool: True if setup was successful
    """
    if not HAS_WEBENGINE or not isinstance(content_edit, QWebEngineView):
        return False
        
    # Get stored position if available
    target_position = getattr(document, 'position', 0) if restore_position else 0
    
    # Add a load finished handler to set position
    def on_load_finished(success):
        if success:
            # Apply theme if available
            if theme_manager:
                apply_theme_to_epub(content_edit, theme_manager)
                
            # Restore position if available
            if target_position and target_position > 0:
                logger.info(f"EPUB page loaded, restoring position to {target_position}")
                # Set a series of delayed attempts to restore position
                restore_attempts = [300, 800, 1500]  # Try at different times
                
                for delay in restore_attempts:
                    QTimer.singleShot(delay, lambda: set_webview_position(content_edit, target_position))
    
    # Connect load finished handler
    content_edit.loadFinished.connect(on_load_finished)
    
    # Inject additional script to make sure position tracking works
    def inject_tracking():
        logger.info("Injecting additional position tracking for EPUB")
        tracking_script = """
        (function() {
            // Position tracking
            let lastKnownScrollPosition = 0;
            let ticking = false;
            
            document.addEventListener('scroll', function(e) {
                lastKnownScrollPosition = window.scrollY;
                
                if (!ticking) {
                    window.requestAnimationFrame(function() {
                        // Store position in a global variable
                        window.lastScrollPosition = lastKnownScrollPosition;
                        console.log('EPUB scroll position: ' + lastKnownScrollPosition);
                        ticking = false;
                    });
                    
                    ticking = true;
                }
            });
            
            // Add keyboard navigation tracking
            document.addEventListener('keydown', function(e) {
                // Wait a moment for the page to scroll
                setTimeout(function() {
                    const newPosition = window.scrollY;
                    window.lastScrollPosition = newPosition;
                    console.log('EPUB keyboard scroll position: ' + newPosition);
                }, 100);
            });
            
            // Report that tracking is enabled
            console.log('EPUB position tracking enabled');
            return true;
        })();
        """
        content_edit.page().runJavaScript(tracking_script)
    
    # Run tracking injection after a delay to ensure page is loaded
    QTimer.singleShot(1000, inject_tracking)
    
    # Set up auto-save of position every few seconds
    def auto_save_position():
        save_webview_position(content_edit, document, db_session)
    
    # Set up timer for auto-save (every 5 seconds)
    position_timer = QTimer()
    position_timer.timeout.connect(auto_save_position)
    position_timer.start(5000)  # 5 seconds
    
    # Store the timer on the content_edit so it doesn't get garbage collected
    content_edit.position_timer = position_timer
    
    return True

def set_webview_position(webview, position):
    """Set the scroll position of a webview."""
    if not HAS_WEBENGINE or not isinstance(webview, QWebEngineView):
        return
        
    try:
        logger.debug(f"Setting WebView scroll position to {position}")
        
        # Comprehensive JavaScript to try different scrolling methods
        script = f"""
        (function() {{
            // Try multiple scrolling methods for best compatibility
            window.scrollTo(0, {position});
            window.scrollTo({{top: {position}, behavior: 'auto'}});
            
            // For legacy browsers
            document.body.scrollTop = {position};
            document.documentElement.scrollTop = {position};
            
            // Record the position
            window.lastScrollPosition = {position};
            
            // Return the actual scroll position after trying to set it
            return window.scrollY || window.pageYOffset || document.documentElement.scrollTop;
        }})();
        """
        
        # Execute the script and log the result
        webview.page().runJavaScript(script, lambda actual_pos: 
            logger.debug(f"WebView position set to {actual_pos}")
        )
    except Exception as e:
        logger.exception(f"Error setting WebView position: {e}")

def save_webview_position(webview, document, db_session):
    """Save the current scroll position of a webview to document."""
    if not HAS_WEBENGINE or not isinstance(webview, QWebEngineView):
        return
        
    try:
        # Function to handle the position value from JavaScript
        def handle_position(pos):
            if isinstance(pos, (int, float)) and pos > 0:
                # Only update if position changed significantly (more than 10 pixels)
                current_pos = getattr(document, 'position', 0) or 0
                if abs(pos - current_pos) > 10:
                    document.position = int(pos)
                    db_session.commit()
                    logger.debug(f"Saved EPUB position: {pos} for {document.title}")
        
        # Get current scroll position
        webview.page().runJavaScript(
            "window.lastScrollPosition !== undefined ? window.lastScrollPosition : (window.scrollY || window.pageYOffset || document.documentElement.scrollTop);",
            handle_position
        )
    except Exception as e:
        logger.exception(f"Error saving WebView position: {e}")

def apply_theme_to_epub(webview, theme_manager):
    """Apply the current theme to an EPUB webview."""
    if not HAS_WEBENGINE or not isinstance(webview, QWebEngineView):
        return
    
    try:
        logger.debug("Applying theme to EPUB content")
        is_dark = theme_manager.current_theme == "dark"
        
        # Create custom CSS based on the current theme
        colors = theme_manager.DEFAULT_DARK_COLORS if is_dark else theme_manager.DEFAULT_LIGHT_COLORS
        
        # Create a CSS for the theme
        theme_css = f"""
        :root {{
            --bg-color: {colors['base']};
            --text-color: {colors['text']};
            --link-color: {colors['link']};
            --highlight-color: {colors['highlight']};
            --highlight-text-color: {colors['highlightedText']};
            --accent-color: {colors['highlight']};
        }}
        
        body {{
            background-color: var(--bg-color) !important;
            color: var(--text-color) !important;
        }}
        
        p, div, span, h1, h2, h3, h4, h5, h6, li {{
            color: var(--text-color) !important;
        }}
        
        a, a:visited {{
            color: var(--link-color) !important;
        }}
        
        ::selection {{
            background-color: var(--highlight-color) !important;
            color: var(--highlight-text-color) !important;
        }}
        """
        
        # Inject CSS into the page
        script = f"""
        (function() {{
            // Remove any existing theme CSS
            let existingStyle = document.getElementById('incrementum-theme-style');
            if (existingStyle) {{
                existingStyle.remove();
            }}
            
            // Add new theme CSS
            let style = document.createElement('style');
            style.id = 'incrementum-theme-style';
            style.textContent = `{theme_css}`;
            document.head.appendChild(style);
            
            console.log('Applied {"dark" if is_dark else "light"} theme to EPUB content');
            return true;
        }})();
        """
        
        webview.page().runJavaScript(script, lambda result: 
            logger.debug(f"Theme applied to EPUB: {result}")
        )
    except Exception as e:
        logger.exception(f"Error applying theme to EPUB: {e}") 