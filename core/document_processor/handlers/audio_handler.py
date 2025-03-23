# core/document_processor/handlers/audio_handler.py

import os
import logging
import time
from typing import Dict, Any, Optional, Tuple
import mimetypes
from pathlib import Path
import requests
import tempfile
from urllib.parse import urlparse
import subprocess
import json

from core.document_processor.handlers.base_handler import DocumentHandler

logger = logging.getLogger(__name__)

class AudioHandler(DocumentHandler):
    """Handler for audio files like MP3, WAV, FLAC, etc."""
    
    SUPPORTED_EXTENSIONS = ['.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac']
    
    def __init__(self):
        """Initialize the audio handler."""
        mimetypes.init()
        
    def extract_metadata(self, file_path: str) -> Dict[str, Any]:
        """
        Extract metadata from an audio file.
        
        Args:
            file_path: Path to the audio file
            
        Returns:
            Dictionary containing metadata
        """
        metadata = {
            "title": os.path.basename(file_path),
            "author": "",
            "description": "",
            "source_url": "",
            "duration": 0,
        }
        
        try:
            # Try to get file size
            file_size = os.path.getsize(file_path)
            metadata["file_size"] = file_size
            
            # Get file extension
            _, ext = os.path.splitext(file_path)
            metadata["format"] = ext.lower()[1:]  # Remove the leading dot
            
            # Try to extract audio metadata using ffprobe (part of ffmpeg)
            if self._is_command_available("ffprobe"):
                cmd = [
                    "ffprobe",
                    "-v", "quiet",
                    "-print_format", "json",
                    "-show_format",
                    "-show_streams",
                    file_path
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    probe_data = json.loads(result.stdout)
                    
                    # Extract format information
                    if "format" in probe_data:
                        fmt = probe_data["format"]
                        
                        # Get duration
                        if "duration" in fmt:
                            metadata["duration"] = float(fmt["duration"])
                        
                        # Get tags (title, artist, etc.)
                        if "tags" in fmt:
                            tags = fmt["tags"]
                            
                            if "title" in tags:
                                metadata["title"] = tags["title"]
                            
                            if "artist" in tags:
                                metadata["author"] = tags["artist"]
                            elif "ARTIST" in tags:
                                metadata["author"] = tags["ARTIST"]
                                
                            if "album" in tags:
                                metadata["album"] = tags["album"]
                            elif "ALBUM" in tags:
                                metadata["album"] = tags["ALBUM"]
            
        except Exception as e:
            logger.error(f"Error extracting audio metadata: {e}")
            
        return metadata
        
    def extract_content(self, file_path: str) -> Dict[str, Any]:
        """
        Extract content from an audio file.
        For audio files, this returns basic metadata since there is no text content.
        
        Args:
            file_path: Path to the audio file
            
        Returns:
            Dictionary with metadata about the audio
        """
        metadata = self.extract_metadata(file_path)
        
        return {
            "metadata": metadata,
            "content": f"Audio file: {metadata.get('title', os.path.basename(file_path))}",
            "type": "audio"
        }
    
    def download_from_url(self, url: str) -> Tuple[Optional[str], Dict[str, Any]]:
        """
        Download an audio file from a URL.
        
        Args:
            url: URL of the audio file
            
        Returns:
            Tuple containing the local file path and metadata
        """
        try:
            # Parse URL to get the filename
            parsed_url = urlparse(url)
            filename = os.path.basename(parsed_url.path)
            
            # If no filename, create a random one with mp3 extension
            if not filename or '.' not in filename:
                filename = f"downloaded_audio_{int(time.time())}.mp3"
            
            # Create a temporary file to save the downloaded content
            with tempfile.NamedTemporaryFile(suffix=os.path.splitext(filename)[1], delete=False) as temp_file:
                temp_path = temp_file.name
                
                # Download the file
                response = requests.get(url, stream=True)
                response.raise_for_status()  # Raise exception for HTTP errors
                
                # Write content to file
                for chunk in response.iter_content(chunk_size=8192):
                    temp_file.write(chunk)
            
            # Extract metadata from the downloaded file
            metadata = self.extract_metadata(temp_path)
            metadata["source_url"] = url
            
            # Return the temp path and metadata
            return temp_path, metadata
            
        except Exception as e:
            logger.exception(f"Failed to download audio from URL: {e}")
            return None, {"error": str(e)}
    
    @staticmethod
    def _is_command_available(cmd: str) -> bool:
        """Check if a command is available in the system PATH."""
        try:
            subprocess.run(
                ["which", cmd], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                check=False
            )
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            return False 