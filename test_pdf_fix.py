# test_pdf_fix.py
import os
import sys
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Mock classes and functions for testing
class Document:
    def __init__(self, file_path, content_type="pdf", title="Test Document"):
        self.id = 1
        self.file_path = file_path
        self.content_type = content_type
        self.title = title
        self.position = 0

class Session:
    def __init__(self):
        self.committed = False
        
    def commit(self):
        self.committed = True
        logger.info("Database session committed")
    
    def query(self, *args):
        return self
        
    def filter(self, *args):
        return []
        
    def get(self, *args):
        return None

def test_file_not_found_handling():
    """Test how our code handles missing PDF files."""
    from ui.pdf_view import PDFViewWidget
    
    # Create a mock document with a non-existent file
    doc = Document("/tmp/nonexistent_file.pdf")
    
    # Create session
    session = Session()
    
    try:
        # Create a PDFViewWidget with the mock document
        view = PDFViewWidget(doc, session)
        
        # Call the _load_pdf method
        view._load_pdf()
        
        logger.info("Test failed: Expected FileNotFoundError exception not raised")
        return False
    except FileNotFoundError as e:
        logger.info(f"Correctly raised FileNotFoundError: {e}")
        return True
    except Exception as e:
        logger.error(f"Unexpected exception: {e}")
        return False

def create_temp_pdf():
    """Create a temporary PDF file for testing."""
    try:
        import fitz  # PyMuPDF
        
        # Create a temporary PDF
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        
        # Add some text
        text_rect = fitz.Rect(100, 100, 400, 150)
        page.insert_text(text_rect.tl, "Test PDF for Incrementum", fontsize=15)
        
        # Create tmp directory if it doesn't exist
        os.makedirs("/tmp/pdf_test", exist_ok=True)
        
        # Save the PDF
        pdf_path = "/tmp/pdf_test/test_doc.pdf"
        doc.save(pdf_path)
        doc.close()
        
        logger.info(f"Created test PDF at {pdf_path}")
        return pdf_path
    except Exception as e:
        logger.error(f"Error creating test PDF: {e}")
        return None

def test_valid_pdf_loading():
    """Test loading a valid PDF file."""
    try:
        # First create a test PDF
        pdf_path = create_temp_pdf()
        if not pdf_path:
            logger.error("Failed to create test PDF")
            return False
            
        from ui.pdf_view import PDFViewWidget
        
        # Create a mock document with the test file
        doc = Document(pdf_path)
        
        # Create session
        session = Session()
        
        try:
            # Create a PDFViewWidget with the mock document
            view = PDFViewWidget(doc, session)
            
            # Call the _load_pdf method
            view._load_pdf()
            
            logger.info("Successfully loaded test PDF")
            return True
        except Exception as e:
            logger.error(f"Failed to load PDF: {e}")
            return False
    except Exception as e:
        logger.error(f"Unexpected error in test: {e}")
        return False

def main():
    """Run the tests."""
    logger.info("Starting PDF fix tests")
    
    # Test file not found handling
    result1 = test_file_not_found_handling()
    
    # Test valid PDF loading
    result2 = test_valid_pdf_loading()
    
    # Report results
    logger.info(f"File not found handling test: {'PASSED' if result1 else 'FAILED'}")
    logger.info(f"Valid PDF loading test: {'PASSED' if result2 else 'FAILED'}")
    
    if result1 and result2:
        logger.info("All tests PASSED")
        return 0
    else:
        logger.error("Some tests FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 