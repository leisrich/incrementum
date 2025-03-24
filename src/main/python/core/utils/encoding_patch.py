# This patch will update the _load_text method in the DocumentView class
# to handle different text file encodings.

# Create a file named "encoding_patch.py" with this content:

import os
import sys
import re

def patch_document_view():
    """
    Patch the DocumentView._load_text method to handle different encodings.
    """
    document_view_path = os.path.join('ui', 'document_view.py')
    
    if not os.path.exists(document_view_path):
        print(f"Error: Could not find {document_view_path}")
        return False
    
    # Read the current file
    with open(document_view_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find the _load_text method
    pattern = r'def _load_text\(self\):(.*?)(?=def |$)'
    match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        print("Error: Could not find the _load_text method in DocumentView")
        return False
    
    old_method = match.group(0)
    
    # Define the new method with improved encoding handling
    new_method = '''def _load_text(self):
        """Load text document content."""
        try:
            # Try UTF-8 first
            try:
                with open(self.document.file_path, 'r', encoding='utf-8') as file:
                    text = file.read()
            except UnicodeDecodeError:
                # If UTF-8 fails, try other common encodings
                encodings = ['latin-1', 'windows-1252', 'iso-8859-1', 'cp1252']
                
                for encoding in encodings:
                    try:
                        with open(self.document.file_path, 'r', encoding=encoding) as file:
                            text = file.read()
                        logger.info(f"Successfully read file using {encoding} encoding")
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    # If all encodings fail, read as binary and decode as best as possible
                    with open(self.document.file_path, 'rb') as file:
                        binary_data = file.read()
                    
                    # Try to decode with errors='replace' to replace invalid characters
                    text = binary_data.decode('utf-8', errors='replace')
                    logger.warning("Using fallback decoding with replacement characters")
            
            self.content_text = text
            self.content_edit.setText(text)
            
        except Exception as e:
            logger.exception(f"Error loading text: {e}")
            self.content_edit.setText(f"Error loading text: {str(e)}")
'''
    
    # Replace the old method with the new one
    new_content = content.replace(old_method, new_method)
    
    # Write the updated content back to the file
    with open(document_view_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"Successfully patched {document_view_path} to handle different text encodings")
    return True

if __name__ == "__main__":
    if patch_document_view():
        print("Patch applied successfully.")
    else:
        print("Failed to apply patch.")
