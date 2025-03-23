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
                
        # User agent for direct requests
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36"
    
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
            # Check if file exists first
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                
                # Check if the content.json file exists in the parent directory
                parent_dir = os.path.dirname(file_path)
                json_path = os.path.join(parent_dir, 'content.json')
                
                if os.path.exists(json_path):
                    logger.info(f"Found content.json, using that instead: {json_path}")
                    with open(json_path, 'r', encoding='utf-8') as f:
                        content = f.read()
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
                            
                        return result
                else:
                    result['text'] = f"File not found: {file_path}. The temporary web content may have been cleaned up."
                    logger.warning(f"Neither {file_path} nor {json_path} exist.")
                    return result
            
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
            result['text'] = f"Error extracting content: {str(e)}"
        
        return result
    
    def _download_images(self, jina_data: Dict[str, Any], base_folder: str) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
        """
        Download images from the Jina data and save them to the specified folder.
        
        Args:
            jina_data: Data from Jina API
            base_folder: Folder to save images to
            
        Returns:
            Tuple of (list of image metadata, mapping of original URLs to local path)
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
    
    def download_from_url(self, url: str, document_path: Optional[str] = None, progress_callback=None) -> Tuple[Optional[str], Dict[str, Any]]:
        """
        Download a webpage using Jina.ai API and save associated images.
        If Jina API fails, fall back to direct web scraping.
        
        Args:
            url: URL to download
            document_path: Path to save document (if None, creates a temporary directory)
            progress_callback: Callback for progress updates
            
        Returns:
            Tuple of (path to downloaded file, metadata dictionary)
        """
        metadata = {'source_url': url, 'source_type': 'jina_web'}
        
        try:
            if not self.api_key:
                raise ValueError("Jina API key not configured")
                
            if progress_callback:
                progress_callback(10, "Initializing download...")
                
            # Create temp folder for download
            if document_path is None:
                temp_dir = tempfile.mkdtemp(prefix='jina_web_')
                document_path = os.path.join(temp_dir, "index.html")
            else:
                temp_dir = os.path.join(os.path.dirname(document_path), "temp_download")
                os.makedirs(temp_dir, exist_ok=True)
            
            # Try using Jina API first
            try:
                # Prepare request
                api_url = "https://api.jina.ai/v1/describe"
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                data = {
                    "url": url,
                    "extType": "full"
                }
                
                if progress_callback:
                    progress_callback(20, "Sending request to Jina.ai...")
                
                # Make request
                response = requests.post(api_url, json=data, headers=headers)
                
                if response.status_code != 200:
                    logger.error(f"Jina API error: {response.status_code} {response.text}")
                    
                    # If the API returned a 404, fall back to direct scraping
                    if response.status_code == 404:
                        logger.info("Jina API returned 404, falling back to direct web scraping")
                        if progress_callback:
                            progress_callback(30, "Jina API unavailable, falling back to direct web scraping...")
                        return self._download_directly(url, temp_dir, progress_callback)
                    else:
                        raise ValueError(f"Failed to fetch URL with Jina: {response.status_code}")
                
                if progress_callback:
                    progress_callback(50, "Processing response...")
                    
                # Process response
                jina_data = response.json()
                
                # Save response to content.json for future reference
                json_path = os.path.join(temp_dir, "content.json")
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(jina_data, f, indent=2, ensure_ascii=False)
                
                # Extract HTML content
                html_content = jina_data.get("html", "")
                if not html_content:
                    raise ValueError("No HTML content returned from Jina")
                    
                # Save HTML content to file
                index_file = os.path.join(temp_dir, "index.html")
                with open(index_file, "w", encoding="utf-8") as f:
                    f.write(html_content)
                
                if progress_callback:
                    progress_callback(70, "Downloading images...")
                    
                # Download images
                images, image_map = self._download_images(jina_data, temp_dir)
                
                # Replace image URLs in HTML
                if image_map:
                    soup = BeautifulSoup(html_content, "lxml")
                    
                    for img in soup.find_all("img"):
                        src = img.get("src", "")
                        if src in image_map:
                            img["src"] = image_map[src]
                            img["data-original-src"] = src
                    
                    # Save modified HTML
                    with open(index_file, "w", encoding="utf-8") as f:
                        f.write(str(soup))
                
                if progress_callback:
                    progress_callback(90, "Finalizing...")
                    
                # Save metadata
                full_metadata = {
                    "url": url,
                    "title": jina_data.get("title", ""),
                    "description": jina_data.get("description", ""),
                    "author": jina_data.get("author", ""),
                    "date": jina_data.get("date", ""),
                    "source_url": url,
                    "source_type": "jina_web",
                    "creation_date": datetime.now(),
                    "modification_date": datetime.now(),
                    "saved_dir": temp_dir,
                    "html_path": index_file,
                    "image_count": len(images),
                    "content_type": "html"
                }
                
                # Save plain text version
                text_content = jina_data.get("text", "")
                if text_content:
                    with open(os.path.join(temp_dir, "content.txt"), "w", encoding="utf-8") as f:
                        f.write(text_content)
                else:
                    # Extract text from HTML
                    soup = BeautifulSoup(html_content, "lxml")
                    text_content = soup.get_text(separator="\n")
                    with open(os.path.join(temp_dir, "content.txt"), "w", encoding="utf-8") as f:
                        f.write(text_content)
                
                if progress_callback:
                    progress_callback(100, "Download complete")
                    
                # Save main content text to a file that can be used directly for summarization
                main_content = self._extract_main_content(jina_data, html_content)
                if main_content:
                    with open(os.path.join(temp_dir, "main_content.txt"), "w", encoding="utf-8") as f:
                        f.write(main_content)
                
                # Return the path to the index.html and the metadata
                return index_file, full_metadata
                
            except Exception as e:
                logger.warning(f"Jina API failed: {e}, falling back to direct web scraping")
                if progress_callback:
                    progress_callback(30, "Jina API failed, falling back to direct web scraping...")
                return self._download_directly(url, temp_dir, progress_callback)
                
        except Exception as e:
            logger.exception(f"Error downloading from URL: {e}")
            if progress_callback:
                progress_callback(100, f"Error: {str(e)}")
            return None, metadata
    
    def _download_directly(self, url: str, temp_dir: str, progress_callback=None) -> Tuple[Optional[str], Dict[str, Any]]:
        """
        Download a webpage directly using requests and BeautifulSoup instead of Jina API.
        
        Args:
            url: URL to download
            temp_dir: Directory to save files
            progress_callback: Callback for progress updates
            
        Returns:
            Tuple of (path to downloaded file, metadata dictionary)
        """
        try:
            if progress_callback:
                progress_callback(40, "Downloading webpage directly...")
                
            # Prepare headers
            headers = {
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Cache-Control": "max-age=0"
            }
            
            # Download the webpage
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            # Process the HTML content
            html_content = response.text
            soup = BeautifulSoup(html_content, "lxml")
            
            if progress_callback:
                progress_callback(60, "Processing HTML content...")
                
            # Save the HTML content
            index_file = os.path.join(temp_dir, "index.html")
            with open(index_file, "w", encoding="utf-8") as f:
                f.write(str(soup))
                
            # Extract metadata
            title = soup.title.string if soup.title else ""
            description = ""
            meta_desc = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
            if meta_desc:
                description = meta_desc.get("content", "")
                
            author = ""
            meta_author = soup.find("meta", attrs={"name": "author"}) or soup.find("meta", attrs={"property": "author"})
            if meta_author:
                author = meta_author.get("content", "")
                
            # Create images directory
            images_dir = os.path.join(temp_dir, "images")
            os.makedirs(images_dir, exist_ok=True)
            
            if progress_callback:
                progress_callback(70, "Downloading images...")
                
            # Download images
            image_count = 0
            for img in soup.find_all("img"):
                src = img.get("src", "")
                if not src:
                    continue
                    
                # Convert relative URLs to absolute
                if not src.startswith(("http://", "https://")):
                    src = urljoin(url, src)
                    
                try:
                    # Generate filename for the image
                    img_filename = f"image_{image_count}_{os.path.basename(urlparse(src).path)}"
                    if not img_filename or img_filename == "image_0_":
                        img_filename = f"image_{image_count}.jpg"
                        
                    img_path = os.path.join(images_dir, img_filename)
                    
                    # Download the image
                    img_response = requests.get(src, headers=headers, timeout=10, stream=True)
                    if img_response.status_code == 200:
                        with open(img_path, "wb") as img_file:
                            img_response.raw.decode_content = True
                            shutil.copyfileobj(img_response.raw, img_file)
                            
                        # Update image source in HTML
                        img["src"] = os.path.join("images", img_filename)
                        img["data-original-src"] = src
                        image_count += 1
                except Exception as img_error:
                    logger.warning(f"Failed to download image {src}: {img_error}")
            
            # Save updated HTML with local image paths
            with open(index_file, "w", encoding="utf-8") as f:
                f.write(str(soup))
                
            # Extract text content
            text_content = soup.get_text(separator="\n")
            with open(os.path.join(temp_dir, "content.txt"), "w", encoding="utf-8") as f:
                f.write(text_content)
                
            if progress_callback:
                progress_callback(90, "Extracting main content...")
                
            # Extract main content
            main_content = self._extract_main_content_from_html(soup)
            if main_content:
                with open(os.path.join(temp_dir, "main_content.txt"), "w", encoding="utf-8") as f:
                    f.write(main_content)
                    
            # Create metadata
            full_metadata = {
                "url": url,
                "title": title,
                "description": description,
                "author": author,
                "date": "",
                "source_url": url,
                "source_type": "direct_web",
                "creation_date": datetime.now(),
                "modification_date": datetime.now(),
                "saved_dir": temp_dir,
                "html_path": index_file,
                "image_count": image_count,
                "content_type": "html"
            }
            
            if progress_callback:
                progress_callback(100, "Download complete")
                
            return index_file, full_metadata
            
        except Exception as e:
            logger.exception(f"Error in direct download: {e}")
            raise
    
    def _extract_main_content_from_html(self, soup: BeautifulSoup) -> str:
        """
        Extract the main content from an HTML page using heuristics.
        
        Args:
            soup: BeautifulSoup object of the HTML
            
        Returns:
            Extracted main content text
        """
        # Remove unwanted elements
        for element in soup.select("nav, header, footer, aside, script, style, [role=banner], [role=navigation], .header, .footer, .sidebar, .navigation, #header, #footer, #sidebar, #navigation"):
            element.decompose()
            
        # Try to find main content
        main_content = None
        
        # Look for common content containers
        for selector in ["article", "main", "[role=main]", ".content", "#content", ".post", ".article"]:
            elements = soup.select(selector)
            if elements:
                # Use the largest content container
                main_content = max(elements, key=lambda x: len(x.get_text()))
                break
                
        if not main_content:
            # Find the element with most text
            paragraphs = soup.find_all("p")
            if paragraphs:
                # Get the parent that contains the most paragraphs
                parents = {}
                for p in paragraphs:
                    parent = p.parent
                    if parent not in parents:
                        parents[parent] = 0
                    parents[parent] += 1
                    
                if parents:
                    main_content = max(parents.keys(), key=lambda x: parents[x])
            
        if not main_content:
            # Fallback to body if no main content container found
            main_content = soup.body
            
        if main_content:
            # Clean the main content
            for element in main_content.select("script, style, iframe, .ads, .advertisement, #ads"):
                element.decompose()
                
            return main_content.get_text(separator="\n").strip()
            
        return ""

    def _extract_main_content(self, jina_data: Dict[str, Any], html_content: str) -> str:
        """
        Extract the main content from Jina response or HTML.
        
        Args:
            jina_data: Data from Jina API
            html_content: HTML content
            
        Returns:
            Extracted main content text
        """
        # First try to get text directly from Jina response
        if "text" in jina_data and jina_data["text"]:
            return jina_data["text"]
            
        # If Jina didn't provide text, extract from HTML
        soup = BeautifulSoup(html_content, "lxml")
        
        # Remove unwanted elements
        for element in soup.select("nav, header, footer, aside, script, style, [role=banner], [role=navigation]"):
            element.decompose()
            
        # Try to find main content
        main_content = None
        
        # Look for common content containers
        for selector in ["article", "main", "[role=main]", ".content", "#content", ".post", ".article"]:
            elements = soup.select(selector)
            if elements:
                # Use the largest content container
                main_content = max(elements, key=lambda x: len(x.get_text()))
                break
                
        if not main_content:
            # Fallback to body if no main content container found
            main_content = soup.body
            
        if main_content:
            return main_content.get_text(separator="\n").strip()
        else:
            # Last resort: get all text
            return soup.get_text(separator="\n").strip()

    def _add_base_tag(self, html_content: str, url: str) -> str:
        """Add a base tag to the HTML to ensure proper resource loading."""
        if not html_content:
            return html_content
            
        # Parse the HTML
        soup = BeautifulSoup(html_content, 'lxml')
        
        # Remove existing base tags
        for base in soup.find_all('base'):
            base.decompose()
            
        # Create a new base tag and add it to the head
        head = soup.head
        if not head:
            # Create head if it doesn't exist
            head = soup.new_tag('head')
            if soup.html:
                soup.html.insert(0, head)
            else:
                # If there's no html tag, create one
                html = soup.new_tag('html')
                html.append(head)
                soup.append(html)
        
        # Add the base tag as the first element in head
        base = soup.new_tag('base')
        base['href'] = url
        head.insert(0, base)
        
        return str(soup)

    def _download_css_files(self, jina_data: Dict[str, Any], resources_dir: str, base_url: str) -> Dict[str, str]:
        """Download CSS files and return a mapping of original URLs to local paths."""
        css_map = {}
        css_dir = os.path.join(resources_dir, 'css')
        os.makedirs(css_dir, exist_ok=True)
        
        # Create directory for CSS files
        if 'html' not in jina_data:
            return css_map
            
        # Parse HTML to find CSS links
        soup = BeautifulSoup(jina_data['html'], 'lxml')
        
        # Process stylesheet links
        for i, link in enumerate(soup.find_all('link', rel='stylesheet')):
            href = link.get('href')
            if not href:
                continue
                
            try:
                # Make URL absolute
                if not urlparse(href).netloc:
                    css_url = urljoin(base_url, href)
                else:
                    css_url = href
                    
                # Skip data URLs
                if css_url.startswith('data:'):
                    continue
                    
                # Create local filename
                filename = f"style_{i}_{os.path.basename(urlparse(css_url).path)}"
                filename = re.sub(r'[^\w\-\.]', '_', filename)
                if not filename.endswith('.css'):
                    filename += '.css'
                    
                local_path = os.path.join(css_dir, filename)
                
                # Download CSS
                response = requests.get(css_url, timeout=10)
                if response.status_code == 200:
                    with open(local_path, 'wb') as css_file:
                        css_file.write(response.content)
                        
                    # Add to map
                    css_map[href] = os.path.join('resources/css', filename)
                    
            except Exception as e:
                logger.warning(f"Failed to download CSS file {href}: {e}")
                
        # Process inline styles
        for i, style in enumerate(soup.find_all('style')):
            if style.string:
                try:
                    # Create filename for inline style
                    filename = f"inline_style_{i}.css"
                    local_path = os.path.join(css_dir, filename)
                    
                    # Save the inline style
                    with open(local_path, 'w', encoding='utf-8') as css_file:
                        css_file.write(style.string)
                        
                except Exception as e:
                    logger.warning(f"Failed to save inline style: {e}")
                    
        return css_map
        
    def _download_js_files(self, jina_data: Dict[str, Any], resources_dir: str, base_url: str) -> Dict[str, str]:
        """Download JavaScript files and return a mapping of original URLs to local paths."""
        js_map = {}
        js_dir = os.path.join(resources_dir, 'js')
        os.makedirs(js_dir, exist_ok=True)
        
        if 'html' not in jina_data:
            return js_map
            
        # Parse HTML to find script tags
        soup = BeautifulSoup(jina_data['html'], 'lxml')
        
        # Process script tags with src
        for i, script in enumerate(soup.find_all('script', src=True)):
            src = script.get('src')
            if not src:
                continue
                
            try:
                # Make URL absolute
                if not urlparse(src).netloc:
                    js_url = urljoin(base_url, src)
                else:
                    js_url = src
                    
                # Skip data URLs
                if js_url.startswith('data:'):
                    continue
                    
                # Create local filename
                filename = f"script_{i}_{os.path.basename(urlparse(js_url).path)}"
                filename = re.sub(r'[^\w\-\.]', '_', filename)
                if not filename.endswith('.js'):
                    filename += '.js'
                    
                local_path = os.path.join(js_dir, filename)
                
                # Download JavaScript
                response = requests.get(js_url, timeout=10)
                if response.status_code == 200:
                    with open(local_path, 'wb') as js_file:
                        js_file.write(response.content)
                        
                    # Add to map
                    js_map[src] = os.path.join('resources/js', filename)
                    
            except Exception as e:
                logger.warning(f"Failed to download JavaScript file {src}: {e}")
                
        # Process inline scripts
        for i, script in enumerate(soup.find_all('script')):
            if script.string and not script.has_attr('src'):
                try:
                    # Create filename for inline script
                    filename = f"inline_script_{i}.js"
                    local_path = os.path.join(js_dir, filename)
                    
                    # Save the inline script
                    with open(local_path, 'w', encoding='utf-8') as js_file:
                        js_file.write(script.string)
                        
                except Exception as e:
                    logger.warning(f"Failed to save inline script: {e}")
                    
        return js_map
        
    def _update_html_with_local_resources(self, html_content: str, resource_map: Dict[str, str], 
                                           tag_name: str, attr_name: str) -> str:
        """Update HTML to use local resources instead of remote ones."""
        if not html_content or not resource_map:
            return html_content
            
        soup = BeautifulSoup(html_content, 'lxml')
        
        # Update resources
        for tag in soup.find_all(tag_name):
            resource_path = tag.get(attr_name)
            if resource_path and resource_path in resource_map:
                tag[attr_name] = resource_map[resource_path]
                tag['data-local'] = 'true'
                
        return str(soup)

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
            # Check if content is empty or just an error message
            if not content or (len(content) < 200 and "Error:" in content or "File not found:" in content):
                logger.error(f"Invalid content for LLM processing: {content[:100]}...")
                return "Error: Unable to extract content from the provided URL. Please check if the URL is valid and accessible."
                
            # Get the first 50,000 characters of content to avoid token limits
            truncated_content = content[:50000] if len(content) > 50000 else content
            
            # Return the extracted content for processing by the LLM service
            return truncated_content
            
        except Exception as e:
            logger.exception(f"Error processing content with LLM: {e}")
            return f"Error: Failed to process content for summarization: {str(e)}" 