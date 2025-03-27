"""PDF utility functions for document processing and manipulation."""

import logging
import fitz  # PyMuPDF
from typing import Optional, List, Tuple, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

class PDFHighlight:
    """Represents a highlight in a PDF document."""
    def __init__(self, page_num: int, rect: List[float], color: Tuple[float, float, float] = (1, 1, 0)):
        """Initialize a highlight.
        
        Args:
            page_num (int): Page number (0-based)
            rect (List[float]): Rectangle coordinates [x0, y0, x1, y1]
            color (Tuple[float, float, float]): RGB color values (0-1), default yellow
        """
        self.page_num = page_num
        self.rect = rect
        self.color = color

def get_pdf_text(pdf_path: str, page_num: Optional[int] = None) -> str:
    """Extract text from a PDF file.
    
    Args:
        pdf_path (str): Path to the PDF file
        page_num (Optional[int]): Specific page number to extract (0-based). If None, extracts all pages.
        
    Returns:
        str: Extracted text content
    
    Raises:
        FileNotFoundError: If PDF file doesn't exist
        ValueError: If invalid page number
        Exception: For other PDF processing errors
    """
    try:
        # Convert path to Path object for better handling
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
            
        doc = fitz.open(str(pdf_path))
        
        if page_num is not None:
            # Extract from specific page
            if not (0 <= page_num < doc.page_count):
                raise ValueError(f"Invalid page number {page_num}. Document has {doc.page_count} pages.")
            return doc[page_num].get_text()
        else:
            # Extract from all pages
            return "\n".join(page.get_text() for page in doc)
            
    except Exception as e:
        logger.exception(f"Error extracting text from PDF {pdf_path}: {e}")
        raise
    finally:
        if 'doc' in locals():
            doc.close()

def get_pdf_text_in_rect(pdf_path: str, page_num: int, rect: List[float]) -> str:
    """Extract text from a specific rectangle area in a PDF page.
    
    Args:
        pdf_path (str): Path to the PDF file
        page_num (int): Page number (0-based)
        rect (List[float]): Rectangle coordinates [x0, y0, x1, y1]
        
    Returns:
        str: Extracted text from the specified area
    """
    try:
        doc = fitz.open(pdf_path)
        page = doc[page_num]
        return page.get_text("text", clip=rect)
    except Exception as e:
        logger.exception(f"Error extracting text from rect in PDF {pdf_path}: {e}")
        return ""
    finally:
        if 'doc' in locals():
            doc.close()

def add_highlight(pdf_path: str, highlight: PDFHighlight) -> bool:
    """Add a highlight to a PDF page.
    
    Args:
        pdf_path (str): Path to the PDF file
        highlight (PDFHighlight): Highlight to add
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        doc = fitz.open(pdf_path)
        page = doc[highlight.page_num]
        
        # Create highlight annotation
        annot = page.add_highlight_annot(highlight.rect)
        annot.set_colors(stroke=highlight.color)
        annot.update()
        
        # Save changes
        doc.save(pdf_path)
        return True
        
    except Exception as e:
        logger.exception(f"Error adding highlight to PDF {pdf_path}: {e}")
        return False
    finally:
        if 'doc' in locals():
            doc.close()

def get_pdf_metadata(pdf_path: str) -> Dict[str, Any]:
    """Extract metadata from a PDF file.
    
    Args:
        pdf_path (str): Path to the PDF file
        
    Returns:
        Dict[str, Any]: Dictionary containing metadata fields
    """
    try:
        doc = fitz.open(pdf_path)
        metadata = {
            'title': doc.metadata.get('title', ''),
            'author': doc.metadata.get('author', ''),
            'subject': doc.metadata.get('subject', ''),
            'keywords': doc.metadata.get('keywords', ''),
            'creator': doc.metadata.get('creator', ''),
            'producer': doc.metadata.get('producer', ''),
            'page_count': doc.page_count,
            'file_size': Path(pdf_path).stat().st_size,
            'format': 'PDF ' + doc.metadata.get('format', ''),
        }
        return metadata
    except Exception as e:
        logger.exception(f"Error extracting metadata from PDF {pdf_path}: {e}")
        return {}
    finally:
        if 'doc' in locals():
            doc.close()

def get_pdf_toc(pdf_path: str) -> List[Dict[str, Any]]:
    """Extract table of contents (outline) from a PDF file.
    
    Args:
        pdf_path (str): Path to the PDF file
        
    Returns:
        List[Dict[str, Any]]: List of TOC entries with page numbers
    """
    try:
        doc = fitz.open(pdf_path)
        toc = doc.get_toc()
        return [{'level': level, 'title': title, 'page': page} for level, title, page in toc]
    except Exception as e:
        logger.exception(f"Error extracting TOC from PDF {pdf_path}: {e}")
        return []
    finally:
        if 'doc' in locals():
            doc.close()

def merge_pdfs(input_paths: List[str], output_path: str) -> bool:
    """Merge multiple PDF files into a single PDF.
    
    Args:
        input_paths (List[str]): List of input PDF file paths
        output_path (str): Path for the merged output PDF
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        doc = fitz.open()
        for path in input_paths:
            with fitz.open(path) as src:
                doc.insert_pdf(src)
        doc.save(output_path)
        return True
    except Exception as e:
        logger.exception(f"Error merging PDFs: {e}")
        return False
    finally:
        if 'doc' in locals():
            doc.close()

def split_pdf(input_path: str, output_dir: str, pages_per_file: int = 1) -> List[str]:
    """Split a PDF file into multiple files.
    
    Args:
        input_path (str): Input PDF file path
        output_dir (str): Directory for output files
        pages_per_file (int): Number of pages per output file
        
    Returns:
        List[str]: List of created file paths
    """
    try:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        doc = fitz.open(input_path)
        base_name = Path(input_path).stem
        output_files = []
        
        for i in range(0, doc.page_count, pages_per_file):
            out_doc = fitz.open()
            out_doc.insert_pdf(doc, from_page=i, to_page=min(i + pages_per_file - 1, doc.page_count - 1))
            
            output_path = output_dir / f"{base_name}_part_{i//pages_per_file + 1}.pdf"
            out_doc.save(str(output_path))
            output_files.append(str(output_path))
            out_doc.close()
            
        return output_files
    except Exception as e:
        logger.exception(f"Error splitting PDF {input_path}: {e}")
        return []
    finally:
        if 'doc' in locals():
            doc.close()

def rotate_pdf_page(pdf_path: str, page_num: int, degrees: int) -> bool:
    """Rotate a specific page in a PDF file.
    
    Args:
        pdf_path (str): Path to the PDF file
        page_num (int): Page number to rotate (0-based)
        degrees (int): Rotation angle (90, 180, or 270)
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        doc = fitz.open(pdf_path)
        page = doc[page_num]
        page.set_rotation(degrees)
        doc.save(pdf_path)
        return True
    except Exception as e:
        logger.exception(f"Error rotating PDF page: {e}")
        return False
    finally:
        if 'doc' in locals():
            doc.close()

def get_page_dimensions(pdf_path: str, page_num: int = 0) -> Tuple[float, float]:
    """Get the dimensions of a PDF page.
    
    Args:
        pdf_path (str): Path to the PDF file
        page_num (int): Page number (0-based)
        
    Returns:
        Tuple[float, float]: Width and height in points
    """
    try:
        doc = fitz.open(pdf_path)
        page = doc[page_num]
        rect = page.rect
        return rect.width, rect.height
    except Exception as e:
        logger.exception(f"Error getting PDF page dimensions: {e}")
        return (0, 0)
    finally:
        if 'doc' in locals():
            doc.close()

def add_bookmark(pdf_path: str, title: str, page_num: int) -> bool:
    """Add a bookmark (outline entry) to a PDF file.
    
    Args:
        pdf_path (str): Path to the PDF file
        title (str): Bookmark title
        page_num (int): Page number (0-based)
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        doc = fitz.open(pdf_path)
        toc = doc.get_toc()
        # Add new entry at the end with level 1
        toc.append([1, title, page_num + 1])  # Page numbers in TOC are 1-based
        doc.set_toc(toc)
        doc.save(pdf_path)
        return True
    except Exception as e:
        logger.exception(f"Error adding bookmark to PDF: {e}")
        return False
    finally:
        if 'doc' in locals():
            doc.close()

def extract_images(pdf_path: str, output_dir: str, min_size: int = 100) -> List[str]:
    """Extract images from a PDF file.
    
    Args:
        pdf_path (str): Path to the PDF file
        output_dir (str): Directory to save extracted images
        min_size (int): Minimum image size in pixels
        
    Returns:
        List[str]: List of saved image file paths
    """
    try:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        doc = fitz.open(pdf_path)
        image_files = []
        
        for page_num in range(doc.page_count):
            page = doc[page_num]
            image_list = page.get_images(full=True)
            
            for img_idx, img_info in enumerate(image_list):
                xref = img_info[0]
                base_image = doc.extract_image(xref)
                
                if base_image:
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]
                    
                    # Save image if it meets minimum size
                    if len(image_bytes) > min_size:
                        image_path = output_dir / f"page_{page_num + 1}_img_{img_idx + 1}.{image_ext}"
                        with open(image_path, "wb") as f:
                            f.write(image_bytes)
                        image_files.append(str(image_path))
        
        return image_files
    except Exception as e:
        logger.exception(f"Error extracting images from PDF: {e}")
        return []
    finally:
        if 'doc' in locals():
            doc.close()

# Example usage
if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    
    # Example PDF file
    pdf_file = "example.pdf"
    
    try:
        # Extract text
        text = get_pdf_text(pdf_file)
        print(f"Extracted text length: {len(text)}")
        
        # Get metadata
        metadata = get_pdf_metadata(pdf_file)
        print(f"PDF Metadata: {metadata}")
        
        # Add highlight
        highlight = PDFHighlight(
            page_num=0,
            rect=[100, 100, 200, 120],
            color=(1, 1, 0)  # Yellow
        )
        if add_highlight(pdf_file, highlight):
            print("Highlight added successfully")
            
    except Exception as e:
        logger.error(f"Error processing PDF: {e}")
