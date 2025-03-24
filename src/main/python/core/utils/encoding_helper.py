# core/utils/encoding_helper.py

import logging
import chardet
from typing import Union, Optional, BinaryIO, TextIO

logger = logging.getLogger(__name__)

def detect_encoding(content: bytes) -> str:
    """
    Detect encoding of binary content.
    
    Args:
        content: Binary content to analyze
        
    Returns:
        Detected encoding or 'utf-8' as fallback
    """
    try:
        # Use chardet to detect encoding
        result = chardet.detect(content)
        encoding = result['encoding']
        confidence = result['confidence']
        
        if encoding and confidence > 0.7:
            return encoding
        
        # If detection is uncertain, use common encodings
        return 'utf-8'
    except Exception as e:
        logger.warning(f"Error detecting encoding: {e}")
        return 'utf-8'

def decode_safely(content: Union[bytes, str, None], 
                 default_encoding: str = 'utf-8') -> str:
    """
    Safely decode content to string, trying multiple encodings if needed.
    
    Args:
        content: Content to decode (bytes, str, or None)
        default_encoding: Encoding to try first
        
    Returns:
        Decoded string or empty string if input is None
    """
    if content is None:
        return ""
    
    if isinstance(content, str):
        return content
    
    if isinstance(content, bytes):
        # Try the specified encoding first
        try:
            return content.decode(default_encoding)
        except UnicodeDecodeError:
            # Detect encoding
            detected_encoding = detect_encoding(content)
            
            if detected_encoding != default_encoding:
                try:
                    return content.decode(detected_encoding)
                except UnicodeDecodeError:
                    pass
            
            # Try common fallback encodings
            for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1', 'utf-16']:
                try:
                    return content.decode(encoding)
                except UnicodeDecodeError:
                    continue
            
            # Last resort: decode with replacement
            return content.decode('latin-1', errors='replace')
    
    # For other types, convert to string
    return str(content)

def safe_read_file(file_path: str) -> str:
    """
    Safely read a text file with automatic encoding detection.
    
    Args:
        file_path: Path to the file
        
    Returns:
        File content as string
    """
    try:
        # First read as binary to detect encoding
        with open(file_path, 'rb') as f:
            content = f.read()
        
        # Detect encoding
        encoding = detect_encoding(content)
        
        # Decode with detected encoding
        return decode_safely(content, encoding)
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {e}")
        return ""

def safe_open(file_path: str, mode: str = 'r') -> Union[TextIO, BinaryIO, None]:
    """
    Safely open a file with automatic encoding detection for text modes.
    
    Args:
        file_path: Path to the file
        mode: Open mode ('r', 'w', 'rb', etc.)
        
    Returns:
        File object or None if there was an error
    """
    try:
        if 'b' in mode:
            # Binary mode, no encoding needed
            return open(file_path, mode)
        
        # Text mode, detect encoding
        if 'r' in mode:
            # Reading, need to detect encoding
            with open(file_path, 'rb') as f:
                content = f.read(10000)  # Read first 10KB for detection
            
            encoding = detect_encoding(content)
            return open(file_path, mode, encoding=encoding)
        else:
            # Writing, use UTF-8
            return open(file_path, mode, encoding='utf-8')
    except Exception as e:
        logger.error(f"Error opening file {file_path}: {e}")
        return None
