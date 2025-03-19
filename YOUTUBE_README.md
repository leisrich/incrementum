# YouTube Support in Incrementum

This guide explains how YouTube video support works in Incrementum and how to troubleshoot common issues.

## Overview

Incrementum can import and view YouTube videos, with position tracking that remembers where you left off watching.

### Features

- Import YouTube videos via URL
- Save and restore watch position
- Extract video metadata (title, author)
- Create extracts from YouTube videos

## Recent Fixes

The YouTube position tracking system has been improved with the following fixes:

1. **Reliable WebChannel Connection**: Fixed the JavaScript-to-Python connection that was causing "backend not available for saving" errors
2. **Better Error Handling**: Added robust error handling with detailed status messages
3. **Multiple Save Methods**: Implemented various ways to save position including:
   - Automatic background saving every 5 seconds (when position changes)
   - Manual save button
   - Save on pause/end
   - Save before closing
4. **Visual Feedback**: Added visual indicators when position is saved
5. **Fallback Mechanisms**: Implemented fallback tracking if WebChannel connection fails
6. **Method Naming Fix**: Renamed `_save_position` to `savePosition` to fix "not a function" errors in JavaScript (methods with leading underscores aren't exposed properly)

## Troubleshooting

### If videos don't load or position isn't saved:

1. **Check YouTube video ID**:
   - When importing, make sure you're using a valid YouTube URL format
   - Supported formats: 
     - https://www.youtube.com/watch?v=VIDEO_ID
     - https://youtu.be/VIDEO_ID
     - https://www.youtube.com/embed/VIDEO_ID

2. **Test with the test script**:
   Run the standalone YouTube timestamp test script to verify that timestamp tracking works:
   ```
   cd ~/Code/incrementum
   python test_youtube.py
   ```

3. **Debugging**:
   - Check the log files for errors related to YouTube loading
   - Look at the status message at the bottom of the video player
   - Use the "Run Debug Tests" button in the test script

### Common Errors

1. **"_save_position is not a function" Error**:
   - This has been fixed by renaming Python methods to not start with underscores
   - Methods with leading underscores aren't properly exposed to JavaScript via QWebChannel
   - If you see this error, make sure you're using the latest version of the code

2. **"Backend not available for saving"**:
   - This indicates a connection issue between JavaScript and Python
   - Try clicking the Save button again after a few seconds
   - Check the console for more detailed error messages

### Manual position saving

If automatic position saving isn't working, you can:

1. Use the "Save Position" button that appears below the video
2. Click on the video tab before closing the application to trigger save_position

## Technical Details

YouTube videos are loaded in a WebView using a combination of:

1. A custom HTML page with YouTube iframe embed
2. JavaScript to track the playback position
3. A PyQt WebChannel to communicate between JavaScript and Python
4. A database position field to store the timestamp

When a video is loaded, the application:
- Loads the video metadata from a JSON file or extracts it from the URL
- Creates a WebView with the HTML template
- Sets up position tracking via JavaScript
- Restores the last saved position if available

The position is saved:
- Every 5 seconds while playing (if position changed by more than 3 seconds)
- When the video is paused or ended
- When the user clicks the Save Position button
- When the document tab is closed
- Before the application exits

## Testing YouTube Support

You can run the YouTube test script to verify integration:

```
cd ~/Code/incrementum
python test_youtube.py
```

This script creates a test environment with a sample YouTube video, allowing you to test position saving and restoration without affecting your main application data. 