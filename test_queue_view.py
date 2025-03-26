#!/usr/bin/env python3
# test_queue_view.py - Simple test script to verify QueueView class

import sys
import os
import inspect
from PyQt6.QtWidgets import QApplication

# Add the parent directory to the path so we can import the app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    # Import the QueueView class
    from ui.queue_view import QueueView
    
    # Check if the class has the required methods
    print("Checking QueueView class methods...")
    
    methods = [name for name, _ in inspect.getmembers(QueueView, predicate=inspect.isfunction)]
    
    # Check for critical methods
    critical_methods = [
        "_create_ui",
        "_load_queue_data",
        "_load_knowledge_tree",
        "_apply_theme",
        "_apply_tree_theme"
    ]
    
    missing_methods = [method for method in critical_methods if method not in methods]
    
    if missing_methods:
        print(f"ERROR: The following methods are missing: {missing_methods}")
    else:
        print("SUCCESS: All critical methods are present in the QueueView class.")
    
    # Print all available methods for reference
    print("\nAvailable methods in QueueView class:")
    for method in sorted(methods):
        print(f"  - {method}")
    
except ImportError as e:
    print(f"ERROR: Could not import QueueView class: {e}")
except Exception as e:
    print(f"ERROR: {e}")

print("\nTest completed.") 