// Enhanced position tracking for document view
(function() {
    // Store last known position to avoid excessive updates
    let lastReportedPosition = 0;
    
    // Report position with minimal threshold changes
    function reportScrollPosition() {
        const position = window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;
        
        // Only report if position changed significantly (more than 50px)
        if (Math.abs(position - lastReportedPosition) > 50) {
            lastReportedPosition = position;
            
            // Report to Qt if available
            if (window.qt && window.qt.positionChanged) {
                window.qt.positionChanged(position);
            }
            
            // Fallback storage in localStorage
            try {
                const docId = document.documentElement.getAttribute('data-document-id');
                if (docId) {
                    localStorage.setItem(`document_position_${docId}`, position);
                }
            } catch (e) {
                console.error('Could not save position to localStorage:', e);
            }
        }
    }
    
    // Throttled scroll event handler
    let scrollTimer = null;
    window.addEventListener('scroll', function() {
        if (scrollTimer !== null) {
            clearTimeout(scrollTimer);
        }
        scrollTimer = setTimeout(reportScrollPosition, 300);
    });
    
    // Report position on page unload
    window.addEventListener('beforeunload', reportScrollPosition);
    
    // Report position periodically (every 30 seconds)
    setInterval(reportScrollPosition, 30000);
    
    // Report position on content load
    document.addEventListener('DOMContentLoaded', function() {
        // Short delay to ensure document has finished rendering
        setTimeout(reportScrollPosition, 500);
    });
    
    // Special handling for EPUBs
    if (document.querySelector('.epub-container, .epub-view, .epub-content')) {
        // Look for EPUB specific elements
        const epubElements = document.querySelectorAll('.epub-container, .epub-view, .epub-content');
        
        // Add scroll handlers to each EPUB container
        epubElements.forEach(function(element) {
            element.addEventListener('scroll', function() {
                if (scrollTimer !== null) {
                    clearTimeout(scrollTimer);
                }
                scrollTimer = setTimeout(reportScrollPosition, 300);
            });
        });
    }
    
    // Utility function to restore position (callable from external code)
    window.restoreDocumentPosition = function(position) {
        if (position && position > 0) {
            // Try standard scrolling first
            window.scrollTo(0, position);
            
            // Check for EPUB containers
            const epubElements = document.querySelectorAll('.epub-container, .epub-view, .epub-content');
            epubElements.forEach(function(element) {
                element.scrollTop = position;
            });
            
            // If using epub.js
            if (typeof window.epub !== 'undefined' && window.epub.goToPosition) {
                window.epub.goToPosition(position);
            }
            
            console.log(`Restored position to ${position}`);
            return true;
        }
        return false;
    };
    
    // Provide a function to get current position
    window.getCurrentPosition = function() {
        return window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;
    };
    
    console.log('Document position tracking initialized');
})();
