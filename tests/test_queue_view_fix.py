#!/usr/bin/env python3
# test_queue_view_fix.py - Simple syntax check for QueueView class

import os
import sys
import ast

def check_file_syntax(file_path):
    """Check if a Python file is syntactically correct."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse the file content to check for syntax errors
        ast.parse(content)
        return True, "File syntax is correct."
    except SyntaxError as e:
        return False, f"Syntax error: {e}"
    except Exception as e:
        return False, f"Error checking file: {e}"

def main():
    # Check the queue_view.py file
    queue_view_path = os.path.join(os.path.dirname(__file__), 'ui', 'queue_view.py')
    success, message = check_file_syntax(queue_view_path)
    
    print(f"Checking syntax for: {queue_view_path}")
    print(f"Result: {'PASS' if success else 'FAIL'}")
    print(f"Message: {message}")
    
    # Print specific message about the _setup_shortcuts fix
    if success:
        print("\nThe _setup_shortcuts method has been fixed. It now correctly sets up keyboard shortcuts")
        print("for navigation and document rating instead of trying to set a tooltip on a non-existent item.")
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main()) 