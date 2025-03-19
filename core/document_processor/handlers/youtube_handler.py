# core/document_processor/handlers/youtube_handler.py

import os
import re
import logging
import tempfile
import json
from typing import Dict, Any, Optional, Tuple
import urllib.parse
import requests

from .base_handler import DocumentHandler

logger = logging.getLogger(__name__)

class YouTubeHandler(DocumentHandler):
    """Handler for YouTube videos."""
    
    def __init__(self):
        super().__init__()
        self.base_data_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
            'data', 'youtube_videos'
        )
        # Create directory if it doesn't exist
        os.makedirs(self.base_data_dir, exist_ok=True)
    
    def extract_metadata(self, file_path: str) -> Dict[str, Any]:
        """
        Extract metadata from a YouTube video URL or metadata file.
        
        Args:
            file_path: Path to video metadata file or URL
            
        Returns:
            Dictionary of metadata
        """
        # If it's a URL, we need to download the metadata
        if file_path.startswith('http'):
            video_id = self._extract_video_id(file_path)
            if not video_id:
                return {'title': file_path, 'author': 'Unknown', 'source_url': file_path}
                
            # Check if we already have metadata for this video
            metadata_path = os.path.join(self.base_data_dir, f"{video_id}.json")
            if os.path.exists(metadata_path):
                try:
                    with open(metadata_path, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except Exception as e:
                    logger.error(f"Error reading metadata file: {e}")
            
            # Fetch video info from API
            return self._fetch_video_info(video_id)
        else:
            # If it's a metadata file, read it directly
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error reading metadata file: {e}")
                return {'title': os.path.basename(file_path), 'author': 'Unknown'}
    
    def extract_content(self, file_path: str) -> str:
        """
        Extract content from a YouTube video (description and metadata).
        
        Args:
            file_path: Path to video metadata file or URL
            
        Returns:
            Textual content from video description and metadata
        """
        metadata = self.extract_metadata(file_path)
        
        # Combine metadata into a text representation
        content = f"Title: {metadata.get('title', 'Unknown')}\n"
        content += f"Author: {metadata.get('author', 'Unknown')}\n"
        content += f"Duration: {metadata.get('duration', 'Unknown')}\n\n"
        content += f"Description:\n{metadata.get('description', '')}\n"
        
        return content
    
    def download_from_url(self, url: str) -> Tuple[Optional[str], Dict[str, Any]]:
        """
        Download YouTube video metadata and save to a local file.
        
        Args:
            url: YouTube video URL
            
        Returns:
            Tuple of (local file path, metadata)
        """
        # Extract video ID
        video_id = self._extract_video_id(url)
        if not video_id:
            logger.error(f"Could not extract video ID from URL: {url}")
            return None, {}
        
        # Fetch video metadata
        metadata = self._fetch_video_info(video_id)
        if not metadata:
            return None, {}
        
        # Create data dir if it doesn't exist (in case it was deleted)
        os.makedirs(self.base_data_dir, exist_ok=True)
        
        # Save metadata to file
        metadata_path = os.path.join(self.base_data_dir, f"{video_id}.json")
        try:
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving metadata file: {e}")
            
            # Try to create a temporary file as fallback
            try:
                import tempfile
                fd, temp_path = tempfile.mkstemp(suffix='.json')
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, ensure_ascii=False, indent=2)
                metadata_path = temp_path
                logger.info(f"Created temporary metadata file at {temp_path} as fallback")
            except Exception as temp_error:
                logger.error(f"Error creating temporary metadata file: {temp_error}")
                return None, metadata
        
        return metadata_path, metadata
    
    def _extract_video_id(self, url: str) -> Optional[str]:
        """
        Extract YouTube video ID from a URL.
        
        Args:
            url: YouTube video URL
            
        Returns:
            Video ID if found, None otherwise
        """
        if not url:
            return None
            
        # Check if this is already just a video ID (11 characters)
        if len(url) == 11 and re.match(r'^[A-Za-z0-9_-]{11}$', url):
            return url
            
        # Parse URL
        try:
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
                    
        except Exception as e:
            logger.warning(f"Error parsing YouTube URL: {e}, URL: {url}")
        
        return None
    
    def _fetch_video_info(self, video_id: str) -> Dict[str, Any]:
        """
        Fetch basic video information using public API.
        
        Args:
            video_id: YouTube video ID
            
        Returns:
            Dictionary of video metadata
        """
        # Try to get the video information from YouTube's oEmbed API
        metadata = {}
        
        try:
            oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
            
            # Use a reasonable timeout for API requests
            response = requests.get(oembed_url, timeout=10)
            
            if response.status_code == 200:
                oembed_data = response.json()
                
                # Build metadata
                metadata = {
                    'title': oembed_data.get('title', f'YouTube Video {video_id}'),
                    'author': oembed_data.get('author_name', 'Unknown'),
                    'video_id': video_id,
                    'source_url': f'https://www.youtube.com/watch?v={video_id}',
                    'embed_url': f'https://www.youtube.com/embed/{video_id}',
                    'source_type': 'youtube',
                    'thumbnail_url': oembed_data.get('thumbnail_url', ''),
                    'description': '',  # YouTube oEmbed API doesn't provide description
                    'duration': 'Unknown',  # Duration not available without Data API
                }
            else:
                logger.warning(f"YouTube API returned status code {response.status_code}")
        except requests.RequestException as e:
            logger.warning(f"Request to YouTube API failed: {e}")
        except Exception as e:
            logger.exception(f"Error fetching YouTube video info: {e}")
        
        # If we couldn't get metadata from the API, use basic info
        if not metadata:
            logger.info(f"Using fallback metadata for YouTube video {video_id}")
            metadata = {
                'title': f'YouTube Video {video_id}',
                'author': 'Unknown',
                'video_id': video_id,
                'source_url': f'https://www.youtube.com/watch?v={video_id}',
                'embed_url': f'https://www.youtube.com/embed/{video_id}',
                'source_type': 'youtube'
            }
        
        return metadata 