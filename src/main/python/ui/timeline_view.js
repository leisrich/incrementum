// Document Timeline View
// This script adds a visual timeline to web-based documents

(function() {
    // Configuration
    const config = {
        timelineHeight: 10,
        markerSize: 16,
        progressColor: 'rgba(0, 120, 255, 0.6)',
        backgroundColor: 'rgba(0, 0, 0, 0.2)',
        bookmarkColor: 'rgba(255, 215, 0, 0.8)',
        markerColor: 'rgba(255, 0, 0, 0.6)',
        showLabels: true
    };
    
    // State variables
    let documentHeight = 0;
    let viewportHeight = 0;
    let currentPosition = 0;
    let bookmarks = [];
    let markers = [];
    let timelineElement = null;
    let progressElement = null;
    let markersContainer = null;
    let isDragging = false;
    
    // Initialize the timeline
    function initTimeline() {
        // Calculate document dimensions
        updateDocumentDimensions();
        
        // Create timeline container
        timelineElement = document.createElement('div');
        timelineElement.id = 'document-timeline';
        timelineElement.style.position = 'fixed';
        timelineElement.style.bottom = '0';
        timelineElement.style.left = '0';
        timelineElement.style.width = '100%';
        timelineElement.style.height = `${config.timelineHeight}px`;
        timelineElement.style.backgroundColor = config.backgroundColor;
        timelineElement.style.zIndex = '1000';
        timelineElement.style.cursor = 'pointer';
        
        // Create progress bar
        progressElement = document.createElement('div');
        progressElement.id = 'timeline-progress';
        progressElement.style.position = 'absolute';
        progressElement.style.top = '0';
        progressElement.style.left = '0';
        progressElement.style.height = '100%';
        progressElement.style.backgroundColor = config.progressColor;
        
        // Create markers container
        markersContainer = document.createElement('div');
        markersContainer.id = 'timeline-markers';
        markersContainer.style.position = 'absolute';
        markersContainer.style.top = `${-config.markerSize + config.timelineHeight/2}px`;
        markersContainer.style.left = '0';
        markersContainer.style.width = '100%';
        markersContainer.style.height = '0';
        markersContainer.style.pointerEvents = 'none';
        
        // Add to timeline
        timelineElement.appendChild(progressElement);
        timelineElement.appendChild(markersContainer);
        
        // Add timeline to document
        document.body.appendChild(timelineElement);
        
        // Add event listeners
        timelineElement.addEventListener('click', onTimelineClick);
        timelineElement.addEventListener('mousedown', onTimelineMouseDown);
        document.addEventListener('mousemove', onTimelineMouseMove);
        document.addEventListener('mouseup', onTimelineMouseUp);
        window.addEventListener('scroll', onWindowScroll);
        window.addEventListener('resize', onWindowResize);
        
        // Initialize progress
        updateProgress();
        
        // Load bookmarks
        loadBookmarksFromStorage();
        
        // Update timeline initially and periodically
        updateTimeline();
        setInterval(updateTimeline, 5000);
        
        console.log('Document timeline initialized');
    }
    
    // Update document dimensions
    function updateDocumentDimensions() {
        documentHeight = Math.max(
            document.body.scrollHeight,
            document.documentElement.scrollHeight,
            document.body.offsetHeight,
            document.documentElement.offsetHeight
        );
        viewportHeight = window.innerHeight;
    }
    
    // Update timeline display
    function updateTimeline() {
        updateDocumentDimensions();
        updateProgress();
        renderBookmarks();
        renderMarkers();
    }
    
    // Update progress based on scroll position
    function updateProgress() {
        // Get current scroll position
        currentPosition = window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;
        
        // Calculate progress percentage
        const maxScroll = documentHeight - viewportHeight;
        const progress = maxScroll > 0 ? (currentPosition / maxScroll) * 100 : 0;
        
        // Update progress element
        progressElement.style.width = `${progress}%`;
    }
    
    // Handle click on timeline
    function onTimelineClick(e) {
        if (isDragging) return;
        
        // Calculate target position
        const timelineWidth = timelineElement.offsetWidth;
        const clickX = e.clientX;
        const percent = clickX / timelineWidth;
        
        // Calculate target scroll position
        const maxScroll = documentHeight - viewportHeight;
        const targetPosition = percent * maxScroll;
        
        // Scroll to position
        window.scrollTo({
            top: targetPosition,
            behavior: 'smooth'
        });
    }
    
    // Handle timeline mouse down
    function onTimelineMouseDown(e) {
        isDragging = true;
        onTimelineMouseMove(e);
    }
    
    // Handle timeline mouse move
    function onTimelineMouseMove(e) {
        if (!isDragging) return;
        
        // Calculate target position
        const timelineWidth = timelineElement.offsetWidth;
        const mouseX = Math.max(0, Math.min(e.clientX, timelineWidth));
        const percent = mouseX / timelineWidth;
        
        // Calculate target scroll position
        const maxScroll = documentHeight - viewportHeight;
        const targetPosition = percent * maxScroll;
        
        // Scroll to position immediately
        window.scrollTo(0, targetPosition);
    }
    
    // Handle timeline mouse up
    function onTimelineMouseUp() {
        isDragging = false;
    }
    
    // Handle window scroll
    function onWindowScroll() {
        updateProgress();
    }
    
    // Handle window resize
    function onWindowResize() {
        updateDocumentDimensions();
        updateProgress();
        renderBookmarks();
        renderMarkers();
    }
    
    // Load bookmarks from storage
    function loadBookmarksFromStorage() {
        try {
            // Get document ID
            const docId = document.documentElement.getAttribute('data-document-id');
            if (!docId) return;
            
            // Load from localStorage
            const savedBookmarks = localStorage.getItem(`bookmarks_${docId}`);
            if (savedBookmarks) {
                bookmarks = JSON.parse(savedBookmarks);
            }
        } catch (e) {
            console.error('Error loading bookmarks:', e);
        }
    }
    
    // Render bookmarks on timeline
    function renderBookmarks() {
        // Remove existing bookmark markers
        const existingBookmarks = markersContainer.querySelectorAll('.timeline-bookmark');
        existingBookmarks.forEach(marker => marker.remove());
        
        // Add new bookmark markers
        bookmarks.forEach(bookmark => {
            // Calculate position percentage
            const maxScroll = documentHeight - viewportHeight;
            const percent = maxScroll > 0 ? (bookmark.position / maxScroll) * 100 : 0;
            
            // Create marker
            const marker = document.createElement('div');
            marker.className = 'timeline-bookmark';
            marker.style.position = 'absolute';
            marker.style.top = `-${config.markerSize/2}px`;
            marker.style.left = `${percent}%`;
            marker.style.width = `${config.markerSize/2}px`;
            marker.style.height = `${config.markerSize}px`;
            marker.style.backgroundColor = config.bookmarkColor;
            marker.style.borderRadius = '2px';
            marker.style.transform = 'translateX(-50%)';
            marker.style.pointerEvents = 'all';
            marker.style.cursor = 'pointer';
            
            // Add tooltip
            marker.title = bookmark.note || `Position: ${Math.round(bookmark.position)}`;
            
            // Add click handler
            marker.addEventListener('click', function(e) {
                e.stopPropagation();
                window.scrollTo({
                    top: bookmark.position,
                    behavior: 'smooth'
                });
            });
            
            // Add to container
            markersContainer.appendChild(marker);
        });
    }
    
    // Add a reading marker
    function addMarker(label = '') {
        // Create marker data
        const markerData = {
            position: currentPosition,
            label: label,
            timestamp: new Date().toISOString()
        };
        
        // Add to markers array
        markers.push(markerData);
        
        // Save markers
        saveMarkersToStorage();
        
        // Render markers
        renderMarkers();
        
        return markerData;
    }
    
    // Remove a marker
    function removeMarker(position) {
        // Find and remove marker
        const index = markers.findIndex(m => Math.abs(m.position - position) < 10);
        if (index !== -1) {
            markers.splice(index, 1);
            saveMarkersToStorage();
            renderMarkers();
            return true;
        }
        return false;
    }
    
    // Save markers to storage
    function saveMarkersToStorage() {
        try {
            // Get document ID
            const docId = document.documentElement.getAttribute('data-document-id');
            if (!docId) return;
            
            // Save to localStorage
            localStorage.setItem(`reading_markers_${docId}`, JSON.stringify(markers));
        } catch (e) {
            console.error('Error saving markers:', e);
        }
    }
    
    // Load markers from storage
    function loadMarkersFromStorage() {
        try {
            // Get document ID
            const docId = document.documentElement.getAttribute('data-document-id');
            if (!docId) return;
            
            // Load from localStorage
            const savedMarkers = localStorage.getItem(`reading_markers_${docId}`);
            if (savedMarkers) {
                markers = JSON.parse(savedMarkers);
            }
        } catch (e) {
            console.error('Error loading markers:', e);
        }
    }
    
    // Render markers on timeline
    function renderMarkers() {
        // Remove existing reading markers
        const existingMarkers = markersContainer.querySelectorAll('.timeline-marker');
        existingMarkers.forEach(marker => marker.remove());
        
        // Add new reading markers
        markers.forEach(marker => {
            // Calculate position percentage
            const maxScroll = documentHeight - viewportHeight;
            const percent = maxScroll > 0 ? (marker.position / maxScroll) * 100 : 0;
            
            // Create marker
            const markerElement = document.createElement('div');
            markerElement.className = 'timeline-marker';
            markerElement.style.position = 'absolute';
            markerElement.style.top = `-${config.markerSize/2}px`;
            markerElement.style.left = `${percent}%`;
            markerElement.style.width = `${config.markerSize/3}px`;
            markerElement.style.height = `${config.markerSize}px`;
            markerElement.style.backgroundColor = config.markerColor;
            markerElement.style.borderRadius = '2px';
            markerElement.style.transform = 'translateX(-50%)';
            markerElement.style.pointerEvents = 'all';
            markerElement.style.cursor = 'pointer';
            
            // Add tooltip
            const date = new Date(marker.timestamp);
            const formattedDate = date.toLocaleString();
            markerElement.title = marker.label ? 
                `${marker.label} (${formattedDate})` : 
                `Marker at position ${Math.round(marker.position)} (${formattedDate})`;
            
            // Add click handler
            markerElement.addEventListener('click', function(e) {
                e.stopPropagation();
                
                // Show marker options
                showMarkerOptions(marker, markerElement);
            });
            
            // Add to container
            markersContainer.appendChild(markerElement);
        });
    }
    
    // Show marker options
    function showMarkerOptions(marker, markerElement) {
        // Create options menu
        const menu = document.createElement('div');
        menu.className = 'marker-options-menu';
        menu.style.position = 'absolute';
        menu.style.top = `-${config.markerSize * 5}px`;
        menu.style.left = '0';
        menu.style.transform = 'translateX(-50%)';
        menu.style.backgroundColor = 'white';
        menu.style.border = '1px solid #ccc';
        menu.style.borderRadius = '5px';
        menu.style.boxShadow = '0 2px 10px rgba(0,0,0,0.2)';
        menu.style.zIndex = '2000';
        menu.style.padding = '5px 0';
        menu.style.width = '120px';
        
        // Go to marker
        const gotoItem = document.createElement('div');
        gotoItem.className = 'menu-item';
        gotoItem.innerText = 'Go to Marker';
        gotoItem.style.padding = '5px 10px';
        gotoItem.style.cursor = 'pointer';
        gotoItem.addEventListener('mouseenter', () => gotoItem.style.backgroundColor = '#eee');
        gotoItem.addEventListener('mouseleave', () => gotoItem.style.backgroundColor = 'transparent');
        gotoItem.addEventListener('click', () => {
            window.scrollTo({
                top: marker.position,
                behavior: 'smooth'
            });
            markersContainer.removeChild(menu);
        });
        menu.appendChild(gotoItem);
        
        // Edit label
        const editItem = document.createElement('div');
        editItem.className = 'menu-item';
        editItem.innerText = 'Edit Label';
        editItem.style.padding = '5px 10px';
        editItem.style.cursor = 'pointer';
        editItem.addEventListener('mouseenter', () => editItem.style.backgroundColor = '#eee');
        editItem.addEventListener('mouseleave', () => editItem.style.backgroundColor = 'transparent');
        editItem.addEventListener('click', () => {
            const newLabel = prompt('Enter label for this marker:', marker.label || '');
            if (newLabel !== null) {
                marker.label = newLabel;
                saveMarkersToStorage();
                renderMarkers();
            }
            markersContainer.removeChild(menu);
        });
        menu.appendChild(editItem);
        
        // Add bookmark
        const bookmarkItem = document.createElement('div');
        bookmarkItem.className = 'menu-item';
        bookmarkItem.innerText = 'Add Bookmark';
        bookmarkItem.style.padding = '5px 10px';
        bookmarkItem.style.cursor = 'pointer';
        bookmarkItem.addEventListener('mouseenter', () => bookmarkItem.style.backgroundColor = '#eee');
        bookmarkItem.addEventListener('mouseleave', () => bookmarkItem.style.backgroundColor = 'transparent');
        bookmarkItem.addEventListener('click', () => {
            if (window.qt && window.qt.addBookmark) {
                window.qt.addBookmark(marker.position);
            } else if (typeof addVisualBookmark === 'function') {
                addVisualBookmark(marker.position, marker.label || '');
            }
            markersContainer.removeChild(menu);
        });
        menu.appendChild(bookmarkItem);
        
        // Remove marker
        const removeItem = document.createElement('div');
        removeItem.className = 'menu-item';
        removeItem.innerText = 'Remove Marker';
        removeItem.style.padding = '5px 10px';
        removeItem.style.cursor = 'pointer';
        removeItem.style.color = '#c00';
        removeItem.addEventListener('mouseenter', () => removeItem.style.backgroundColor = '#fee');
        removeItem.addEventListener('mouseleave', () => removeItem.style.backgroundColor = 'transparent');
        removeItem.addEventListener('click', () => {
            removeMarker(marker.position);
            markersContainer.removeChild(menu);
        });
        menu.appendChild(removeItem);
        
        // Position the menu
        const rect = markerElement.getBoundingClientRect();
        menu.style.left = `${rect.left}px`;
        
        // Add to markers container
        markersContainer.appendChild(menu);
        
        // Handle click outside
        const clickHandler = function(e) {
            if (!menu.contains(e.target) && e.target !== markerElement) {
                markersContainer.removeChild(menu);
                document.removeEventListener('click', clickHandler);
            }
        };
        
        // Add delay to avoid immediate close
        setTimeout(() => {
            document.addEventListener('click', clickHandler);
        }, 100);
    }
    
    // Add timeline controls
    function addTimelineControls() {
        // Create controls container
        const controls = document.createElement('div');
        controls.id = 'timeline-controls';
        controls.style.position = 'fixed';
        controls.style.bottom = `${config.timelineHeight + 5}px`;
        controls.style.left = '10px';
        controls.style.zIndex = '1000';
        controls.style.display = 'flex';
        controls.style.gap = '5px';
        
        // Add marker button
        const addMarkerButton = document.createElement('button');
        addMarkerButton.innerText = '📌';
        addMarkerButton.title = 'Add Reading Marker';
        addMarkerButton.style.width = '30px';
        addMarkerButton.style.height = '30px';
        addMarkerButton.style.borderRadius = '50%';
        addMarkerButton.style.border = 'none';
        addMarkerButton.style.backgroundColor = 'rgba(255, 255, 255, 0.8)';
        addMarkerButton.style.cursor = 'pointer';
        addMarkerButton.style.boxShadow = '0 2px 5px rgba(0,0,0,0.2)';
        addMarkerButton.style.fontSize = '16px';
        addMarkerButton.style.display = 'flex';
        addMarkerButton.style.alignItems = 'center';
        addMarkerButton.style.justifyContent = 'center';
        
        addMarkerButton.addEventListener('click', function() {
            const label = prompt('Enter label for this marker (optional):');
            addMarker(label || '');
        });
        
        controls.appendChild(addMarkerButton);
        
        // Toggle labels button
        const toggleLabelsButton = document.createElement('button');
        toggleLabelsButton.innerText = '🏷️';
        toggleLabelsButton.title = 'Toggle Labels';
        toggleLabelsButton.style.width = '30px';
        toggleLabelsButton.style.height = '30px';
        toggleLabelsButton.style.borderRadius = '50%';
        toggleLabelsButton.style.border = 'none';
        toggleLabelsButton.style.backgroundColor = config.showLabels ? 
            'rgba(200, 255, 200, 0.8)' : 'rgba(255, 255, 255, 0.8)';
        toggleLabelsButton.style.cursor = 'pointer';
        toggleLabelsButton.style.boxShadow = '0 2px 5px rgba(0,0,0,0.2)';
        toggleLabelsButton.style.fontSize = '16px';
        toggleLabelsButton.style.display = 'flex';
        toggleLabelsButton.style.alignItems = 'center';
        toggleLabelsButton.style.justifyContent = 'center';
        
        toggleLabelsButton.addEventListener('click', function() {
            config.showLabels = !config.showLabels;
            toggleLabelsButton.style.backgroundColor = config.showLabels ? 
                'rgba(200, 255, 200, 0.8)' : 'rgba(255, 255, 255, 0.8)';
                
            // Update labels visibility
            document.querySelectorAll('.marker-label').forEach(label => {
                label.style.display = config.showLabels ? 'block' : 'none';
            });
        });
        
        controls.appendChild(toggleLabelsButton);
        
        // Add to document
        document.body.appendChild(controls);
    }
    
    // Initialize when document is loaded
    function init() {
        // Load markers
        loadMarkersFromStorage();
        
        // Initialize timeline
        initTimeline();
        
        // Add controls
        addTimelineControls();
    }
    
    // Initialize on document ready
    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        init();
    } else {
        document.addEventListener('DOMContentLoaded', init);
    }
    
    // Expose API to window
    window.documentTimeline = {
        addMarker,
        removeMarker,
        updateTimeline
    };
})();
