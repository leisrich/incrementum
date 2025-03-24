#!/usr/bin/env python
"""
Simple test script for YouTube embedding in Incrementum.
Run this directly to test YouTube video loading without the full app.
"""

import sys
import re
import urllib.parse
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineWidgets import QWebEngineView

# Custom YouTube embed without using the helper module
class MockDocument:
    """Mock document class for testing."""
    def __init__(self):
        self.id = 1
        self.title = "Test YouTube Video"
        self.author = "Test Author"
        self.file_path = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Never Gonna Give You Up
        self.position = 0
        self.source_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

def extract_video_id(url):
    """Extract YouTube video ID from a URL."""
    # Parse URL
    parsed_url = urllib.parse.urlparse(url)
    
    # Check if it's a YouTube URL
    if 'youtube.com' in parsed_url.netloc:
        # Regular youtube.com URL
        query_params = urllib.parse.parse_qs(parsed_url.query)
        if 'v' in query_params:
            return query_params['v'][0]
    elif 'youtu.be' in parsed_url.netloc:
        # Shortened URL
        return parsed_url.path.strip('/')
    
    # Try to find video ID using regex for other URL formats
    patterns = [
        r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})',
        r'(?:youtube\.com\/embed\/)([^"&?\/\s]{11})',
        r'(?:youtube\.com\/watch\?v=)([^"&?\/\s]{11})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None

def main():
    """Run the test application."""
    app = QApplication(sys.argv)
    
    # Create main window
    window = QMainWindow()
    window.setWindowTitle("YouTube Test")
    window.resize(800, 600)
    
    # Create central widget
    central = QWidget()
    layout = QVBoxLayout(central)
    
    # Create web view
    webview = QWebEngineView()
    
    # Get document data
    doc = MockDocument()
    video_id = extract_video_id(doc.source_url)
    if not video_id:
        print("Failed to extract video ID!")
        return
    
    print(f"Found video ID: {video_id}")
    
    # Create direct HTML without helper module
    target_position = doc.position or 0
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{doc.title}</title>
        <style>
            body {{
                margin: 0;
                padding: 0;
                overflow: hidden;
                background-color: #f0f0f0;
                height: 100vh;
                font-family: Arial, sans-serif;
            }}
            .header {{
                padding: 10px;
                background-color: #f9f9f9;
                border-bottom: 1px solid #e0e0e0;
            }}
            .header h1 {{
                margin: 0;
                padding: 0;
                font-size: 18px;
            }}
            .header p {{
                margin: 5px 0 0 0;
                font-size: 14px;
                color: #666;
            }}
            .video-container {{
                width: 100%;
                height: calc(100vh - 60px);
                display: flex;
                justify-content: center;
                align-items: center;
            }}
            iframe {{
                width: 100%;
                height: 100%;
                border: none;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>{doc.title}</h1>
            <p>{doc.author}</p>
        </div>
        <div class="video-container">
            <iframe 
                id="youtube-player"
                src="https://www.youtube.com/embed/{video_id}?autoplay=1&start={target_position}&enablejsapi=1" 
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" 
                allowfullscreen>
            </iframe>
        </div>
    </body>
    </html>
    """
    
    # Load the HTML
    webview.setHtml(html)
    
    # Add to layout
    layout.addWidget(webview)
    
    # Set central widget
    window.setCentralWidget(central)
    
    # Show window
    window.show()
    
    # Run app
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 