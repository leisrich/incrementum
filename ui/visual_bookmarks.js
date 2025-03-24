// Visual bookmarks implementation for web-based documents
(function() {
    // Bookmark data container
    const bookmarks = [];
    
    // Initialize the visual bookmarks system
    function initVisualBookmarks() {
        // Create bookmark panel container
        const panel = document.createElement('div');
        panel.id = 'bookmark-panel';
        panel.style.position = 'fixed';
        panel.style.right = '0';
        panel.style.top = '40%';
        panel.style.transform = 'translateY(-50%)';
        panel.style.backgroundColor = 'rgba(50, 50, 80, 0.6)';
        panel.style.borderRadius = '5px 0 0 5px';
        panel.style.padding = '5px';
        panel.style.zIndex = '1000';
        panel.style.transition = 'opacity 0.3s';
        panel.style.opacity = '0.7';
        panel.style.display = 'none';
        panel.style.flexDirection = 'column';
        panel.style.alignItems = 'center';
        
        // Add hover effect
        panel.addEventListener('mouseenter', function() {
            panel.style.opacity = '1';
        });
        
        panel.addEventListener('mouseleave', function() {
            panel.style.opacity = '0.7';
        });
        
        // Add to document
        document.body.appendChild(panel);
        
        // Add add bookmark button
        const addButton = document.createElement('button');
        addButton.innerText = '📌';
        addButton.title = 'Add Bookmark';
        addButton.style.background = 'none';
        addButton.style.border = 'none';
        addButton.style.fontSize = '20px';
        addButton.style.color = 'white';
        addButton.style.cursor = 'pointer';
        addButton.style.padding = '5px';
        addButton.style.display = 'block';
        addButton.style.width = '30px';
        addButton.style.height = '30px';
        addButton.onclick = function() {
            const position = window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;
            
            // Notify Qt if callback exists
            if (window.qt && window.qt.addBookmark) {
                window.qt.addBookmark(position);
            } else {
                // Fallback - add directly
                addBookmark(position);
            }
        };
        
        panel.appendChild(addButton);
        
        // Show panel after short delay
        setTimeout(() => {
            panel.style.display = 'flex';
        }, 1000);
        
        // Add scroll position indicator
        const scrollIndicator = document.createElement('div');
        scrollIndicator.id = 'scroll-indicator';
        scrollIndicator.style.position = 'fixed';
        scrollIndicator.style.right = '40px';
        scrollIndicator.style.top = '20px';
        scrollIndicator.style.backgroundColor = 'rgba(0, 0, 0, 0.6)';
        scrollIndicator.style.color = 'white';
        scrollIndicator.style.padding = '5px 10px';
        scrollIndicator.style.borderRadius = '15px';
        scrollIndicator.style.fontSize = '12px';
        scrollIndicator.style.opacity = '0';
        scrollIndicator.style.transition = 'opacity 0.3s';
        scrollIndicator.style.zIndex = '1000';
        
        document.body.appendChild(scrollIndicator);
        
        // Update scroll indicator on scroll
        let scrollTimer = null;
        window.addEventListener('scroll', function() {
            const position = window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;
            
            // Show scroll position
            scrollIndicator.innerText = `Position: ${Math.round(position)}`;
            scrollIndicator.style.opacity = '1';
            
            // Hide after delay
            if (scrollTimer !== null) {
                clearTimeout(scrollTimer);
            }
            
            scrollTimer = setTimeout(() => {
                scrollIndicator.style.opacity = '0';
            }, 1500);
        });
    }
    
    // Add a bookmark at the specified position
    function addBookmark(position, note = '') {
        // Create bookmark data
        const bookmark = {
            position: position,
            note: note,
            created: new Date()
        };
        
        // Add to bookmarks array
        bookmarks.push(bookmark);
        
        // Create a visual bookmark marker
        createBookmarkMarker(bookmark);
        
        // Sort bookmarks by position
        bookmarks.sort((a, b) => a.position - b.position);
        
        // Save bookmarks to localStorage
        saveBookmarks();
        
        // Show confirmation
        showNotification('Bookmark added');
        
        return bookmark;
    }
    
    // Create a visual bookmark marker
    function createBookmarkMarker(bookmark) {
        // Get bookmark panel
        const panel = document.getElementById('bookmark-panel');
        if (!panel) return;
        
        // Create marker element
        const marker = document.createElement('div');
        marker.className = 'bookmark-marker';
        marker.dataset.position = bookmark.position;
        marker.style.width = '24px';
        marker.style.height = '24px';
        marker.style.margin = '5px 0';
        marker.style.backgroundColor = 'rgba(0, 120, 255, 0.7)';
        marker.style.border = '2px solid white';
        marker.style.borderRadius = '50%';
        marker.style.cursor = 'pointer';
        marker.style.display = 'flex';
        marker.style.alignItems = 'center';
        marker.style.justifyContent = 'center';
        marker.style.fontSize = '12px';
        marker.style.color = 'white';
        marker.style.position = 'relative';
        
        // Calculate position in document (for visualization)
        const docHeight = Math.max(
            document.body.scrollHeight,
            document.documentElement.scrollHeight,
            document.body.offsetHeight,
            document.documentElement.offsetHeight
        );
        
        // Add the label to show which number bookmark it is
        const index = bookmarks.findIndex(b => b.position === bookmark.position);
        marker.innerText = (index + 1).toString();
        
        // Add tooltip with note
        marker.title = bookmark.note || `Position: ${Math.round(bookmark.position)}`;
        
        // Add click handler
        marker.addEventListener('click', function() {
            // Scroll to bookmark position
            window.scrollTo({
                top: bookmark.position,
                behavior: 'smooth'
            });
        });
        
        // Add context menu
        marker.addEventListener('contextmenu', function(event) {
            event.preventDefault();
            
            // Create context menu
            const menu = document.createElement('div');
            menu.className = 'bookmark-context-menu';
            menu.style.position = 'absolute';
            menu.style.left = (event.clientX + 5) + 'px';
            menu.style.top = (event.clientY + 5) + 'px';
            menu.style.backgroundColor = 'white';
            menu.style.border = '1px solid #ccc';
            menu.style.borderRadius = '5px';
            menu.style.boxShadow = '0 2px 10px rgba(0,0,0,0.2)';
            menu.style.zIndex = '2000';
            menu.style.padding = '5px 0';
            
            // Add menu items
            const gotoItem = document.createElement('div');
            gotoItem.className = 'menu-item';
            gotoItem.innerText = 'Go to Bookmark';
            gotoItem.style.padding = '5px 10px';
            gotoItem.style.cursor = 'pointer';
            gotoItem.addEventListener('mouseenter', () => gotoItem.style.backgroundColor = '#eee');
            gotoItem.addEventListener('mouseleave', () => gotoItem.style.backgroundColor = 'transparent');
            gotoItem.addEventListener('click', () => {
                window.scrollTo({
                    top: bookmark.position,
                    behavior: 'smooth'
                });
                document.body.removeChild(menu);
            });
            menu.appendChild(gotoItem);
            
            const editItem = document.createElement('div');
            editItem.className = 'menu-item';
            editItem.innerText = 'Edit Note';
            editItem.style.padding = '5px 10px';
            editItem.style.cursor = 'pointer';
            editItem.addEventListener('mouseenter', () => editItem.style.backgroundColor = '#eee');
            editItem.addEventListener('mouseleave', () => editItem.style.backgroundColor = 'transparent');
            editItem.addEventListener('click', () => {
                const note = prompt('Enter note for this bookmark:', bookmark.note || '');
                if (note !== null) {
                    bookmark.note = note;
                    marker.title = note || `Position: ${Math.round(bookmark.position)}`;
                    saveBookmarks();
                    
                    // Notify Qt if callback exists
                    if (window.qt && window.qt.updateBookmark) {
                        window.qt.updateBookmark(bookmark.position, note);
                    }
                }
                document.body.removeChild(menu);
            });
            menu.appendChild(editItem);
            
            const removeItem = document.createElement('div');
            removeItem.className = 'menu-item';
            removeItem.innerText = 'Remove Bookmark';
            removeItem.style.padding = '5px 10px';
            removeItem.style.cursor = 'pointer';
            removeItem.style.color = '#c00';
            removeItem.addEventListener('mouseenter', () => removeItem.style.backgroundColor = '#fee');
            removeItem.addEventListener('mouseleave', () => removeItem.style.backgroundColor = 'transparent');
            removeItem.addEventListener('click', () => {
                removeBookmark(bookmark.position);
                document.body.removeChild(menu);
            });
            menu.appendChild(removeItem);
            
            // Add to document
            document.body.appendChild(menu);
            
            // Handle click outside
            const clickHandler = function(e) {
                if (!menu.contains(e.target)) {
                    document.body.removeChild(menu);
                    document.removeEventListener('click', clickHandler);
                }
            };
            
            // Add delay to avoid immediate close
            setTimeout(() => {
                document.addEventListener('click', clickHandler);
            }, 100);
        });
        
        // Add to panel
        panel.appendChild(marker);
        
        // Sort markers by position
        const markers = Array.from(panel.querySelectorAll('.bookmark-marker'));
        markers.sort((a, b) => {
            return parseFloat(a.dataset.position) - parseFloat(b.dataset.position);
        });
        
        // Remove all and add back in order
        markers.forEach(m => panel.removeChild(m));
        markers.forEach((m, i) => {
            m.innerText = (i + 1).toString();
            panel.appendChild(m);
        });
    }
    
    // Remove bookmark at specified position
    function removeBookmark(position) {
        // Find bookmark index
        const index = bookmarks.findIndex(b => b.position === position);
        if (index === -1) return;
        
        // Remove from array
        bookmarks.splice(index, 1);
        
        // Remove marker
        const panel = document.getElementById('bookmark-panel');
        if (panel) {
            const markers = panel.querySelectorAll('.bookmark-marker');
            markers.forEach(marker => {
                if (parseFloat(marker.dataset.position) === position) {
                    panel.removeChild(marker);
                }
            });
            
            // Update marker numbers
            const remainingMarkers = Array.from(panel.querySelectorAll('.bookmark-marker'));
            remainingMarkers.sort((a, b) => {
                return parseFloat(a.dataset.position) - parseFloat(b.dataset.position);
            });
            
            remainingMarkers.forEach((marker, i) => {
                marker.innerText = (i + 1).toString();
            });
        }
        
        // Save bookmarks
        saveBookmarks();
        
        // Notify Qt if callback exists
        if (window.qt && window.qt.removeBookmark) {
            window.qt.removeBookmark(position);
        }
        
        // Show notification
        showNotification('Bookmark removed');
    }
    
    // Save bookmarks to localStorage
    function saveBookmarks() {
        try {
            const docId = document.documentElement.getAttribute('data-document-id');
            if (docId) {
                localStorage.setItem(`bookmarks_${docId}`, JSON.stringify(bookmarks));
            }
        } catch (e) {
            console.error('Error saving bookmarks:', e);
        }
    }
    
    // Load bookmarks from localStorage
    function loadBookmarks() {
        try {
            const docId = document.documentElement.getAttribute('data-document-id');
            if (docId) {
                const saved = localStorage.getItem(`bookmarks_${docId}`);
                if (saved) {
                    const loadedBookmarks = JSON.parse(saved);
                    bookmarks.length = 0; // Clear existing
                    loadedBookmarks.forEach(bookmark => {
                        bookmarks.push(bookmark);
                        createBookmarkMarker(bookmark);
                    });
                }
            }
        } catch (e) {
            console.error('Error loading bookmarks:', e);
        }
    }
    
    // Show notification
    function showNotification(message) {
        // Create notification element if it doesn't exist
        let notification = document.getElementById('bookmark-notification');
        if (!notification) {
            notification = document.createElement('div');
            notification.id = 'bookmark-notification';
            notification.style.position = 'fixed';
            notification.style.bottom = '20px';
            notification.style.left = '50%';
            notification.style.transform = 'translateX(-50%)';
            notification.style.backgroundColor = 'rgba(40, 40, 40, 0.9)';
            notification.style.color = 'white';
            notification.style.padding = '10px 20px';
            notification.style.borderRadius = '20px';
            notification.style.zIndex = '2000';
            notification.style.opacity = '0';
            notification.style.transition = 'opacity 0.3s';
            
            document.body.appendChild(notification);
        }
        
        // Set message and show
        notification.innerText = message;
        notification.style.opacity = '1';
        
        // Hide after delay
        setTimeout(() => {
            notification.style.opacity = '0';
        }, 2000);
    }
    
    // Set document ID (called from Qt)
    window.setDocumentId = function(docId) {
        document.documentElement.setAttribute('data-document-id', docId);
        
        // Load bookmarks after ID is set
        loadBookmarks();
    };
    
    // Provide functions to Qt bridge
    window.addVisualBookmark = addBookmark;
    window.removeVisualBookmark = removeBookmark;
    
    // Initialize when document is loaded
    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        initVisualBookmarks();
    } else {
        document.addEventListener('DOMContentLoaded', initVisualBookmarks);
    }
})();
