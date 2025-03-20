# core/document_processor/handlers/jina_web_handler.py

import os
import logging
import tempfile
import requests
import json
import base64
from typing import Dict, Any, Optional, List, Tuple
from urllib.parse import urlparse, urljoin
from datetime import datetime
from bs4 import BeautifulSoup
import shutil
import re

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
    
    def _download_images(self, jina_data: Dict[str, Any], base_folder: str) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
        """
        Download images from the Jina data and save them to the specified folder.
        
        Args:
            jina_data: Data from Jina API
            base_folder: Folder to save images to
            
        Returns:
            Tuple of (list of image metadata, mapping of original URL to local path)
        """
        image_folder = os.path.join(base_folder, 'images')
        os.makedirs(image_folder, exist_ok=True)
        
        saved_images = []
        image_map = {}  # Maps original URLs to local paths
        
        # Get source URL for building absolute image URLs
        source_url = jina_data.get('url', '')
        
        # Process images from Jina data
        if 'images' in jina_data and isinstance(jina_data['images'], list):
            for i, image_data in enumerate(jina_data['images']):
                if not isinstance(image_data, dict):
                    continue
                    
                try:
                    image_url = image_data.get('url', '')
                    if not image_url:
                        continue
                    
                    # Make URL absolute if it's relative
                    if not urlparse(image_url).netloc and source_url:
                        image_url = urljoin(source_url, image_url)
                    
                    # Create a safe filename from the URL
                    filename = f"image_{i}_{os.path.basename(urlparse(image_url).path)}"
                    filename = re.sub(r'[^\w\-\.]', '_', filename)
                    if not filename.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                        filename += '.jpg'  # Default extension
                    
                    local_path = os.path.join(image_folder, filename)
                    
                    # Download the image
                    response = requests.get(image_url, stream=True, timeout=10)
                    if response.status_code == 200:
                        with open(local_path, 'wb') as img_file:
                            response.raw.decode_content = True
                            shutil.copyfileobj(response.raw, img_file)
                        
                        # Save image metadata
                        image_data['local_path'] = os.path.join('images', filename)
                        saved_images.append(image_data)
                        
                        # Add to image map
                        image_map[image_url] = os.path.join('images', filename)
                    
                except Exception as e:
                    logger.warning(f"Failed to download image {image_url}: {e}")
        
        # Also look for images in the HTML content
        html_content = jina_data.get('html', '')
        if html_content:
            soup = BeautifulSoup(html_content, 'lxml')
            for i, img in enumerate(soup.find_all('img')):
                src = img.get('src', '')
                if not src or src in image_map:
                    continue
                
                try:
                    # Make URL absolute if it's relative
                    if not urlparse(src).netloc and source_url:
                        src = urljoin(source_url, src)
                    
                    # Handle data URLs (base64 encoded images)
                    if src.startswith('data:image/'):
                        # Parse data URL
                        metadata, encoded = src.split(',', 1)
                        image_type = metadata.split(';')[0].split('/')[1]
                        
                        # Create filename for data URL
                        filename = f"inline_image_{i}.{image_type}"
                        local_path = os.path.join(image_folder, filename)
                        
                        # Save the image
                        with open(local_path, 'wb') as img_file:
                            img_file.write(base64.b64decode(encoded))
                        
                        # Add to image map
                        image_map[src] = os.path.join('images', filename)
                        continue
                    
                    # Create a safe filename
                    filename = f"img_{i}_{os.path.basename(urlparse(src).path)}"
                    filename = re.sub(r'[^\w\-\.]', '_', filename)
                    if not filename.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                        filename += '.jpg'
                    
                    local_path = os.path.join(image_folder, filename)
                    
                    # Download the image
                    response = requests.get(src, stream=True, timeout=10)
                    if response.status_code == 200:
                        with open(local_path, 'wb') as img_file:
                            response.raw.decode_content = True
                            shutil.copyfileobj(response.raw, img_file)
                        
                        # Add to image map
                        image_map[src] = os.path.join('images', filename)
                        
                        # Add to saved images if not already included
                        if src not in [img.get('url', '') for img in saved_images]:
                            saved_images.append({
                                'url': src,
                                'local_path': os.path.join('images', filename),
                                'alt': img.get('alt', '')
                            })
                
                except Exception as e:
                    logger.warning(f"Failed to download image {src} from HTML: {e}")
        
        return saved_images, image_map
    
    def _update_html_with_local_images(self, html_content: str, image_map: Dict[str, str]) -> str:
        """
        Update HTML content to use local image paths instead of remote URLs.
        
        Args:
            html_content: Original HTML content
            image_map: Mapping of original URLs to local paths
            
        Returns:
            Updated HTML content
        """
        if not html_content or not image_map:
            return html_content
        
        soup = BeautifulSoup(html_content, 'lxml')
        
        # Update image sources
        for img in soup.find_all('img'):
            src = img.get('src', '')
            if src in image_map:
                img['src'] = image_map[src]
                # Mark as local image
                img['data-local'] = 'true'
        
        # Update CSS backgrounds (this is simplified and might not catch all cases)
        style_tags = soup.find_all('style')
        for style in style_tags:
            css_content = style.string
            if not css_content:
                continue
            
            # Replace URLs in CSS
            for original_url, local_path in image_map.items():
                if original_url in css_content:
                    css_content = css_content.replace(original_url, local_path)
            
            style.string = css_content
        
        # Update inline styles with background images
        for element in soup.find_all(lambda tag: tag.has_attr('style') and 'background' in tag['style']):
            style = element['style']
            for original_url, local_path in image_map.items():
                if original_url in style:
                    element['style'] = style.replace(original_url, local_path)
        
        return str(soup)
    
    def download_from_url(self, url: str) -> Tuple[Optional[str], Dict[str, Any]]:
        """Download a webpage using Jina.ai API and save all associated images."""
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
            
            # Create a temporary directory to store the webpage and its resources
            temp_dir = tempfile.mkdtemp(prefix='jina_web_')
            
            # Download and save images
            saved_images, image_map = self._download_images(jina_data, temp_dir)
            
            # Update the HTML to use local image paths
            if 'html' in jina_data:
                jina_data['html'] = self._update_html_with_local_images(jina_data['html'], image_map)
            
            # Add saved images to the data
            jina_data['saved_images'] = saved_images
            
            # Create a JSON file for metadata and content
            json_path = os.path.join(temp_dir, 'content.json')
            
            # Save the updated content
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(jina_data, f, ensure_ascii=False, indent=2)
            
            # Create an HTML file with the modified content
            html_path = os.path.join(temp_dir, 'index.html')
            if 'html' in jina_data:
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(jina_data['html'])
            
            # Extract basic metadata
            if 'url' in jina_data:
                metadata['source_url'] = jina_data['url']
            
            if 'title' in jina_data:
                metadata['title'] = jina_data['title']
            
            metadata['creation_date'] = datetime.now()
            metadata['modification_date'] = datetime.now()
            metadata['saved_dir'] = temp_dir
            metadata['image_count'] = len(saved_images)
            
            return json_path, metadata
            
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