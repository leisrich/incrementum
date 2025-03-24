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
        
        # Add temp_dir attribute using tempfile module's temp directory
        self.temp_dir = self.base_data_dir
    
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
        Create a metadata file for a YouTube video.
        
        Args:
            url: YouTube video URL
            
        Returns:
            Tuple of (local file path, metadata)
        """
        # Extract video ID from URL
        video_id = self._extract_video_id(url)
        if not video_id:
            logger.error(f"Could not extract video ID from URL: {url}")
            return None, {}
        
        # Fetch video metadata
        try:
            metadata = self._fetch_video_metadata(video_id)
        except Exception as e:
            logger.exception(f"Error fetching video metadata: {e}")
            return None, {}
        
        # Create a temporary JSON file to store metadata
        try:
            # Make sure we have a directory for storing metadata
            os.makedirs(self.temp_dir, exist_ok=True)
            
            file_path = os.path.join(self.temp_dir, f"youtube_{video_id}.json")
            
            # Try to fetch transcript
            logger.info(f"Attempting to fetch transcript for video {video_id}")
            transcript = self.fetch_transcript(video_id)
            
            if transcript:
                logger.info(f"Successfully obtained transcript for {video_id}")
                metadata['transcript'] = transcript
            else:
                logger.warning(f"No transcript available for video {video_id}")
            
            # Store metadata in file
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)
            
            logger.info(f"Created metadata file at {file_path}")
            return file_path, metadata
            
        except Exception as e:
            logger.exception(f"Error creating metadata file: {e}")
            return None, {}
    
    def _fetch_video_metadata(self, video_id: str) -> Dict[str, Any]:
        """Fetch metadata for a YouTube video."""
        # Use YouTube oEmbed API to get basic metadata
        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        
        try:
            response = requests.get(oembed_url)
            response.raise_for_status()
            data = response.json()
            
            # Create metadata dictionary
            metadata = {
                'title': data.get('title', 'Untitled YouTube Video'),
                'author': data.get('author_name', 'Unknown'),
                'video_id': video_id,
                'source_url': f"https://www.youtube.com/watch?v={video_id}",
                'source_type': 'youtube',
                'thumbnail_url': data.get('thumbnail_url', ''),
                'html': data.get('html', ''),
                'width': data.get('width', 640),
                'height': data.get('height', 360)
            }
            
            return metadata
            
        except Exception as e:
            logger.exception(f"Error fetching YouTube metadata: {e}")
            
            # Return basic metadata using video ID
            return {
                'title': f"YouTube Video {video_id}",
                'author': 'Unknown',
                'video_id': video_id,
                'source_url': f"https://www.youtube.com/watch?v={video_id}",
                'source_type': 'youtube'
            }
    
    def _extract_video_id(self, url: str) -> Optional[str]:
        """Extract YouTube video ID from a URL."""
        if not url:
            return None
            
        # Check if input is already a video ID
        if re.match(r'^[a-zA-Z0-9_-]{11}$', url):
            return url
            
        try:
            # Parse the URL
            parsed_url = urllib.parse.urlparse(url)
            
            # List of patterns to match YouTube URLs
            patterns = [
                # Standard YouTube URLs
                r'^(?:https?:\/\/)?(?:www\.)?youtube\.com\/watch\?v=([a-zA-Z0-9_-]{11})',
                # Shortened URLs
                r'^(?:https?:\/\/)?(?:www\.)?youtu\.be\/([a-zA-Z0-9_-]{11})',
                # Embedded URLs
                r'^(?:https?:\/\/)?(?:www\.)?youtube\.com\/embed\/([a-zA-Z0-9_-]{11})'
            ]
            
            # Try each pattern
            for pattern in patterns:
                match = re.match(pattern, url)
                if match:
                    return match.group(1)
            
            # If no match found with regex, try parsing query parameters
            if 'youtube.com' in parsed_url.netloc:
                query_params = urllib.parse.parse_qs(parsed_url.query)
                if 'v' in query_params:
                    return query_params['v'][0]
            
            # Handle youtu.be URLs
            if 'youtu.be' in parsed_url.netloc:
                path = parsed_url.path.lstrip('/')
                if path:
                    return path
            
            return None
            
        except Exception as e:
            logger.exception(f"Error extracting video ID from URL: {e}")
            return None
    
    def fetch_transcript(self, video_id: str) -> Optional[str]:
        """
        Fetch transcript for a YouTube video using the YouTube Data API.
        
        Args:
            video_id: YouTube video ID
            
        Returns:
            Transcript text if available, None otherwise
        """
        try:
            # First try using the YouTube Data API if there's an API key
            api_key = os.environ.get('YOUTUBE_API_KEY')
            if api_key:
                return self._fetch_transcript_with_api(video_id, api_key)
            
            # Fallback to using youtube-transcript-api
            return self._fetch_transcript_with_library(video_id)
        except Exception as e:
            logger.exception(f"Error fetching transcript for video {video_id}: {e}")
            return None
    
    def _fetch_transcript_with_api(self, video_id: str, api_key: str) -> Optional[str]:
        """Fetch transcript using YouTube Data API."""
        try:
            # First, get the caption tracks available for the video
            captions_url = f"https://www.googleapis.com/youtube/v3/captions?part=snippet&videoId={video_id}&key={api_key}"
            response = requests.get(captions_url)
            response.raise_for_status()
            captions_data = response.json()
            
            # Look for English captions or auto-generated captions
            caption_id = None
            for item in captions_data.get('items', []):
                track_kind = item.get('snippet', {}).get('trackKind')
                language = item.get('snippet', {}).get('language', '')
                
                # Prefer English manual captions, then English auto captions
                if track_kind == 'standard' and language == 'en':
                    caption_id = item['id']
                    break
                elif track_kind == 'ASR' and language == 'en' and not caption_id:
                    caption_id = item['id']
            
            if not caption_id:
                logger.warning(f"No suitable captions found for video {video_id}")
                return None
            
            # Now get the caption content
            # Note: Direct download requires authentication with OAuth, 
            # so for simplicity we'll use another library for this part
            return self._fetch_transcript_with_library(video_id)
            
        except Exception as e:
            logger.exception(f"Error fetching transcript with API: {e}")
            return None
    
    def _fetch_transcript_with_library(self, video_id: str) -> Optional[str]:
        """Fetch transcript using youtube-transcript-api library."""
        try:
            # Try to import the library
            try:
                from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
                from youtube_transcript_api.formatters import TextFormatter
            except ImportError:
                logger.warning("youtube-transcript-api not installed. Install with: pip install youtube-transcript-api")
                # Try to install it automatically
                import subprocess
                try:
                    logger.info("Attempting to install youtube-transcript-api automatically...")
                    subprocess.check_call(['pip', 'install', 'youtube-transcript-api'])
                    # Import again after installation
                    from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
                    from youtube_transcript_api.formatters import TextFormatter
                    logger.info("Successfully installed and imported youtube-transcript-api")
                except Exception as pip_error:
                    logger.error(f"Failed to install youtube-transcript-api: {pip_error}")
                    return None
            
            # First try to list available transcripts
            try:
                logger.info(f"Listing available transcripts for video ID: {video_id}")
                transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
                
                # Try to find the best transcript
                transcript = None
                
                # 1. Try English manual transcript first
                for t in transcript_list:
                    if t.language_code == 'en' and not t.is_generated:
                        transcript = t
                        logger.info("Found English manual transcript")
                        break
                
                # 2. Try English auto-generated transcript
                if not transcript:
                    for t in transcript_list:
                        if t.language_code == 'en':
                            transcript = t
                            logger.info("Found English auto-generated transcript")
                            break
                
                # 3. Try any manual transcript
                if not transcript:
                    for t in transcript_list:
                        if not t.is_generated:
                            transcript = t
                            logger.info(f"Found manual transcript in {t.language_code}")
                            break
                
                # 4. Use any available transcript
                if not transcript:
                    transcript = next(transcript_list._transcripts.values().__iter__())
                    logger.info(f"Using first available transcript in {transcript.language_code}")
                
                # Get the transcript
                transcript_data = transcript.fetch()
                logger.info(f"Successfully fetched transcript with {len(transcript_data)} entries")
                
                # Format transcript as text
                formatter = TextFormatter()
                formatted_transcript = formatter.format_transcript(transcript_data)
                logger.info(f"Formatted transcript length: {len(formatted_transcript)}")
                return formatted_transcript
                
            except TranscriptsDisabled:
                logger.warning(f"Transcripts are disabled for video {video_id}")
                return None
            except NoTranscriptFound:
                logger.warning(f"No transcripts found for video {video_id}")
                return None
            except Exception as list_error:
                logger.warning(f"Error listing transcripts: {list_error}")
                # Fallback to direct transcript fetch
                try:
                    logger.info("Falling back to direct transcript fetch...")
                    transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
                    logger.info(f"Found transcript with {len(transcript_list)} entries")
                    
                    # Format transcript as text
                    formatter = TextFormatter()
                    formatted_transcript = formatter.format_transcript(transcript_list)
                    logger.info(f"Formatted transcript length: {len(formatted_transcript)}")
                    return formatted_transcript
                except Exception as direct_error:
                    logger.error(f"Error in direct transcript fetch: {direct_error}")
                    return None
                    
        except Exception as e:
            logger.exception(f"Error fetching transcript with library: {e}")
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