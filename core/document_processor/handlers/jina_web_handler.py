# core/document_processor/handlers/jina_web_handler.py

import os
import logging
import tempfile
import requests
import json
from typing import Dict, Any, Optional, List, Tuple
from urllib.parse import urlparse
from datetime import datetime
from bs4 import BeautifulSoup

from .base_handler import DocumentHandler
from core.utils.settings_manager import SettingsManager

logger = logging.getLogger(__name__)

class JinaWebHandler(DocumentHandler):
    """Handler for processing websites using Jina.ai API."""
    
    def __init__(self, settings_manager: Optional[SettingsManager] = None):
        """Initialize the handler with settings manager for API credentials."""
        self.settings_manager = settings_manager
        # Default API key (can be overridden from settings)
        self.api_key = "jina_80d8d9a6bdd643f3bc68b667fac0b6bezWku0QbPydO0p87xDB3wIKtuIBQW"
        
        # Load API key from settings if available
        if settings_manager:
            saved_key = settings_manager.get_setting("api", "jina_api_key", "")
            if saved_key:
                self.api_key = saved_key
    
    def extract_metadata(self, file_path: str) -> Dict[str, Any]:
        """Extract metadata from a Jina-processed HTML file."""
        metadata = {
            'title': os.path.basename(file_path),
            'author': '',
            'creation_date': None,
            'modification_date': None,
            'source_url': '',
            'source_type': 'jina_web'
        }
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # Try to load as JSON first
                try:
                    jina_data = json.loads(content)
                    # Extract metadata from Jina JSON
                    if 'url' in jina_data:
                        metadata['source_url'] = jina_data['url']
                    if 'title' in jina_data:
                        metadata['title'] = jina_data['title']
                    # Set current time as modification date
                    metadata['modification_date'] = datetime.now()
                    return metadata
                except json.JSONDecodeError:
                    # Not JSON, treat as HTML
                    soup = BeautifulSoup(content, 'lxml')
                    
                    # Extract title
                    if soup.title:
                        metadata['title'] = soup.title.string
                    
                    # Extract author
                    author_meta = soup.find('meta', attrs={'name': 'author'})
                    if author_meta and author_meta.get('content'):
                        metadata['author'] = author_meta['content']
                    
                    # Extract other metadata
                    description_meta = soup.find('meta', attrs={'name': 'description'})
                    if description_meta and description_meta.get('content'):
                        metadata['description'] = description_meta['content']
                
        except Exception as e:
            logger.exception(f"Error extracting Jina web metadata: {e}")
        
        return metadata
    
    def extract_content(self, file_path: str) -> Dict[str, Any]:
        """Extract content from a Jina-processed HTML file."""
        result = {
            'text': '',
            'html': '',
            'elements': [],
            'images': [],
            'jina_data': {}
        }
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
                # Try to load as JSON
                try:
                    jina_data = json.loads(content)
                    result['jina_data'] = jina_data
                    
                    # Extract HTML content
                    if 'html' in jina_data:
                        result['html'] = jina_data['html']
                        soup = BeautifulSoup(jina_data['html'], 'lxml')
                        result['text'] = soup.get_text(separator='\n')
                    
                    # Extract text directly if available
                    if 'text' in jina_data:
                        result['text'] = jina_data['text']
                    
                    # Extract images if available
                    if 'images' in jina_data and isinstance(jina_data['images'], list):
                        result['images'] = jina_data['images']
                    
                    # Extract structured elements
                    if 'html' in jina_data:
                        soup = BeautifulSoup(jina_data['html'], 'lxml')
                        for element in soup.find_all(['h1', 'h2', 'h3', 'p']):
                            result['elements'].append({
                                'type': element.name,
                                'content': element.get_text(),
                                'html': str(element)
                            })
                    
                except json.JSONDecodeError:
                    # Not JSON, treat as HTML
                    soup = BeautifulSoup(content, 'lxml')
                    
                    # Extract text content
                    result['text'] = soup.get_text(separator='\n')
                    
                    # Store original HTML
                    result['html'] = content
                    
                    # Extract elements
                    for element in soup.find_all(['h1', 'h2', 'h3', 'p']):
                        result['elements'].append({
                            'type': element.name,
                            'content': element.get_text(),
                            'html': str(element)
                        })
                
        except Exception as e:
            logger.exception(f"Error extracting Jina web content: {e}")
        
        return result
    
    def download_from_url(self, url: str) -> Tuple[Optional[str], Dict[str, Any]]:
        """Download a webpage using Jina.ai API."""
        metadata = {'source_url': url, 'source_type': 'jina_web'}
        
        try:
            # Prepare Jina.ai API request
            jina_url = f"https://r.jina.ai/{url}"
            
            headers = {
                "Accept": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "X-Engine": "browser",
                "X-With-Generated-Alt": "true",
                "X-With-Images-Summary": "all"
            }
            
            # Make the request to Jina.ai
            response = requests.get(jina_url, headers=headers)
            response.raise_for_status()
            
            # Parse the response
            jina_data = response.json()
            
            # Create a temporary file
            fd, temp_path = tempfile.mkstemp(suffix='.json')
            
            # Save the content
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(jina_data, f, ensure_ascii=False, indent=2)
            
            # Extract basic metadata
            if 'url' in jina_data:
                metadata['source_url'] = jina_data['url']
            
            if 'title' in jina_data:
                metadata['title'] = jina_data['title']
            
            metadata['creation_date'] = datetime.now()
            metadata['modification_date'] = datetime.now()
            
            return temp_path, metadata
            
        except Exception as e:
            logger.exception(f"Error downloading from Jina.ai: {e}")
            return None, metadata

    def process_content_with_llm(self, content: str, settings_manager) -> Optional[str]:
        """
        Process the content with an LLM if requested.
        
        Args:
            content: The content to process
            settings_manager: Settings manager for LLM configuration
            
        Returns:
            Processed content if successful, None otherwise
        """
        try:
            # Don't create dialog here. We need to return the content only
            # and let the main thread handle dialog creation
            return content
            
        except Exception as e:
            logger.exception(f"Error processing content with LLM: {e}")
            return None 