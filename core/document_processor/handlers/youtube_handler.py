# core/document_processor/handlers/youtube_handler.py

import os
import re
import logging
import tempfile
import json
from typing import Dict, Any, Optional, Tuple, List
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
        
        # Directory for playlists
        self.playlists_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
            'data', 'youtube_playlists'
        )
        os.makedirs(self.playlists_dir, exist_ok=True)
        
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
    
    def _extract_playlist_id(self, url: str) -> Optional[str]:
        """Extract YouTube playlist ID from a URL.
        
        Args:
            url: URL that may contain a YouTube playlist ID
            
        Returns:
            Playlist ID if found, None otherwise
        """
        if not url:
            return None
            
        # Check if input is already a playlist ID 
        if re.match(r'^[a-zA-Z0-9_-]{13,42}$', url) and 'PL' in url:
            return url
            
        try:
            # Parse the URL
            parsed_url = urllib.parse.urlparse(url)
            
            # Check if it's a youtube.com URL
            if 'youtube.com' in parsed_url.netloc:
                # Parse query parameters
                query_params = urllib.parse.parse_qs(parsed_url.query)
                
                # Look for 'list' parameter which contains playlist ID
                if 'list' in query_params:
                    return query_params['list'][0]
            
            return None
            
        except Exception as e:
            logger.exception(f"Error extracting playlist ID from URL: {e}")
            return None
    
    def fetch_playlist_metadata(self, playlist_id: str, api_key: str = None) -> Dict[str, Any]:
        """
        Fetch metadata for a YouTube playlist.
        
        Args:
            playlist_id: YouTube playlist ID
            api_key: Optional YouTube API key. If not provided, will try to get from settings
            
        Returns:
            Dictionary containing playlist metadata
        """
        try:
            # Get API key from settings if not provided
            if not api_key:
                from core.utils.settings_manager import SettingsManager
                settings = SettingsManager()
                api_key = settings.get_setting("api", "youtube_api_key")  # Fixed path
            
            if not api_key:
                logger.error("No YouTube API key found")
                return None
                
            # Base URL for playlist items
            base_url = "https://www.googleapis.com/youtube/v3/playlistItems"
            
            # Parameters for the API request
            params = {
                'part': 'snippet,contentDetails',
                'maxResults': 50,  # Max allowed by API
                'playlistId': playlist_id,
                'key': api_key
            }
            
            # Get playlist info first
            playlist_url = "https://www.googleapis.com/youtube/v3/playlists"
            playlist_params = {
                'part': 'snippet',
                'id': playlist_id,
                'key': api_key
            }
            
            playlist_response = requests.get(playlist_url, params=playlist_params)
            playlist_response.raise_for_status()
            playlist_data = playlist_response.json()
            
            if not playlist_data.get('items'):
                logger.error(f"Playlist {playlist_id} not found")
                return None
                
            playlist_info = playlist_data['items'][0]['snippet']
            
            # Initialize metadata
            metadata = {
                'playlist_id': playlist_id,
                'title': playlist_info.get('title', ''),
                'channel_title': playlist_info.get('channelTitle', ''),
                'description': playlist_info.get('description', ''),
                'thumbnail_url': playlist_info.get('thumbnails', {}).get('default', {}).get('url', ''),
                'videos': []
            }
            
            # Get all playlist items
            while True:
                response = requests.get(base_url, params=params)
                response.raise_for_status()
                data = response.json()
                
                # Process items
                for item in data.get('items', []):
                    video_data = {
                        'video_id': item['contentDetails']['videoId'],
                        'title': item['snippet']['title'],
                        'description': item['snippet'].get('description', ''),
                        'thumbnail_url': item['snippet'].get('thumbnails', {}).get('default', {}).get('url', ''),
                        'position': item['snippet']['position'] + 1,  # Make 1-based
                        'published_at': item['snippet'].get('publishedAt')
                    }
                    
                    # Get video duration
                    video_url = "https://www.googleapis.com/youtube/v3/videos"
                    video_params = {
                        'part': 'contentDetails',
                        'id': video_data['video_id'],
                        'key': api_key
                    }
                    
                    video_response = requests.get(video_url, params=video_params)
                    video_response.raise_for_status()
                    video_info = video_response.json()
                    
                    if video_info.get('items'):
                        duration_str = video_info['items'][0]['contentDetails']['duration']
                        # Convert ISO 8601 duration to seconds
                        import isodate
                        duration = int(isodate.parse_duration(duration_str).total_seconds())
                        video_data['duration'] = duration
                    
                    metadata['videos'].append(video_data)
                
                # Check if there are more pages
                if 'nextPageToken' in data:
                    params['pageToken'] = data['nextPageToken']
                else:
                    break
            
            return metadata
            
        except Exception as e:
            logger.exception(f"Error fetching playlist metadata: {e}")
            return None
    
    def fetch_playlist_videos(self, playlist_id: str, api_key: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch videos in a YouTube playlist.
        
        Args:
            playlist_id: YouTube playlist ID
            api_key: YouTube Data API key (optional)
            
        Returns:
            List of video metadata dictionaries
        """
        videos = []
        
        try:
            if not api_key:
                api_key = os.environ.get('YOUTUBE_API_KEY')
                
            if not api_key:
                logger.warning("No YouTube API key available for fetching playlist videos")
                return videos
                
            # Initialize variables for pagination
            next_page_token = None
            position = 1  # 1-based position index
            
            while True:
                # Build URL for playlist items request
                playlist_items_url = (
                    f"https://www.googleapis.com/youtube/v3/playlistItems"
                    f"?part=snippet,contentDetails"
                    f"&maxResults=50"
                    f"&playlistId={playlist_id}"
                    f"&key={api_key}"
                )
                
                # Add page token if we have one
                if next_page_token:
                    playlist_items_url += f"&pageToken={next_page_token}"
                
                # Make API request
                response = requests.get(playlist_items_url, timeout=10)
                
                if response.status_code != 200:
                    logger.warning(f"YouTube API returned status code {response.status_code} for playlist items")
                    break
                    
                data = response.json()
                
                # Process each video in the results
                for item in data.get('items', []):
                    snippet = item.get('snippet', {})
                    content_details = item.get('contentDetails', {})
                    
                    video_id = content_details.get('videoId')
                    if not video_id:
                        continue
                        
                    # Get video details
                    video_metadata = {
                        'video_id': video_id,
                        'title': snippet.get('title', f'Video {position}'),
                        'description': snippet.get('description', ''),
                        'position': position,
                        'thumbnail_url': snippet.get('thumbnails', {}).get('high', {}).get('url', ''),
                        'channel_title': snippet.get('videoOwnerChannelTitle', ''),
                        'published_at': snippet.get('publishedAt', '')
                    }
                    
                    # Fetch additional video details like duration if needed
                    try:
                        video_details_url = f"https://www.googleapis.com/youtube/v3/videos?part=contentDetails&id={video_id}&key={api_key}"
                        video_response = requests.get(video_details_url, timeout=10)
                        
                        if video_response.status_code == 200:
                            video_data = video_response.json()
                            if video_data.get('items'):
                                content_details = video_data['items'][0].get('contentDetails', {})
                                duration_iso = content_details.get('duration', '')  # ISO 8601 duration format
                                
                                # Convert ISO 8601 duration to seconds
                                duration_seconds = self._parse_duration(duration_iso)
                                video_metadata['duration'] = duration_seconds
                    except Exception as e:
                        logger.warning(f"Failed to fetch additional video details for {video_id}: {e}")
                    
                    videos.append(video_metadata)
                    position += 1
                
                # Check if there are more pages
                next_page_token = data.get('nextPageToken')
                if not next_page_token:
                    break
                    
            logger.info(f"Fetched {len(videos)} videos from playlist {playlist_id}")
            return videos
            
        except Exception as e:
            logger.exception(f"Error fetching playlist videos: {e}")
            return videos
    
    def _parse_duration(self, duration_iso: str) -> int:
        """Parse ISO 8601 duration format to seconds.
        
        Args:
            duration_iso: ISO 8601 duration string (e.g., "PT1H30M15S")
            
        Returns:
            Duration in seconds
        """
        if not duration_iso:
            return 0
            
        try:
            # Remove PT prefix
            duration = duration_iso[2:]
            
            hours = 0
            minutes = 0
            seconds = 0
            
            # Extract hours, minutes, seconds
            h_match = re.search(r'(\d+)H', duration)
            if h_match:
                hours = int(h_match.group(1))
                
            m_match = re.search(r'(\d+)M', duration)
            if m_match:
                minutes = int(m_match.group(1))
                
            s_match = re.search(r'(\d+)S', duration)
            if s_match:
                seconds = int(s_match.group(1))
                
            # Calculate total seconds
            return hours * 3600 + minutes * 60 + seconds
            
        except Exception as e:
            logger.warning(f"Error parsing duration {duration_iso}: {e}")
            return 0
    
    def _fetch_playlist_info_fallback(self, playlist_id: str) -> Dict[str, Any]:
        """Fetch basic playlist info without using the YouTube Data API.
        
        Args:
            playlist_id: YouTube playlist ID
            
        Returns:
            Dictionary of playlist metadata
        """
        metadata = {
            'playlist_id': playlist_id,
            'title': f"YouTube Playlist {playlist_id}",
            'channel_title': 'Unknown',
            'description': '',
            'thumbnail_url': '',
            'videos': []
        }
        
        try:
            # Attempt to get information from playlist page
            url = f"https://www.youtube.com/playlist?list={playlist_id}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                html_content = response.text
                
                # Extract title
                title_match = re.search(r'<title>(.*?)</title>', html_content)
                if title_match:
                    metadata['title'] = title_match.group(1).replace(' - YouTube', '')
                
                # Extract channel name
                channel_match = re.search(r'<link itemprop="name" content="(.*?)">', html_content)
                if channel_match:
                    metadata['channel_title'] = channel_match.group(1)
                
                logger.info(f"Fetched basic playlist info for {playlist_id} using fallback method")
                
            return metadata
                
        except Exception as e:
            logger.exception(f"Error in playlist fallback: {e}")
            return metadata
    
    def download_playlist(self, playlist_url: str) -> Tuple[Optional[str], Dict[str, Any]]:
        """Download metadata for a YouTube playlist.
        
        Args:
            playlist_url: URL of YouTube playlist
            
        Returns:
            Tuple of (local file path, metadata)
        """
        # Extract playlist ID from URL
        playlist_id = self._extract_playlist_id(playlist_url)
        if not playlist_id:
            logger.error(f"Could not extract playlist ID from URL: {playlist_url}")
            return None, {}
        
        # Fetch playlist metadata
        try:
            metadata = self.fetch_playlist_metadata(playlist_id)
            
            # Create a directory for this playlist
            playlist_dir = os.path.join(self.playlists_dir, playlist_id)
            os.makedirs(playlist_dir, exist_ok=True)
            
            # Save metadata to file
            metadata_file = os.path.join(playlist_dir, "playlist_metadata.json")
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)
                
            logger.info(f"Saved playlist metadata to {metadata_file}")
            
            return metadata_file, metadata
            
        except Exception as e:
            logger.exception(f"Error downloading playlist: {e}")
            return None, {} 