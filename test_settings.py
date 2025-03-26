#!/usr/bin/env python3
# test_settings.py - Test script for the SettingsManager

import sys
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Add the parent directory to the path so we can import the app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    # Import the SettingsManager class
    from core.utils.settings_manager import SettingsManager
    
    print("Testing SettingsManager class...")
    
    # Create a SettingsManager instance
    settings = SettingsManager()
    
    # Test set_setting and get_setting methods
    section = "test_section"
    key = "test_key"
    value = "test_value"
    
    # Set a test setting
    result = settings.set_setting(section, key, value)
    print(f"Set setting '{section}.{key}' to '{value}': {'Success' if result else 'Failed'}")
    
    # Get the test setting
    retrieved = settings.get_setting(section, key, "default_value")
    print(f"Retrieved '{section}.{key}': '{retrieved}' (Expected: '{value}')")
    
    # Test getting a non-existent setting
    default = "default_value"
    non_existent = settings.get_setting("non_existent", "key", default)
    print(f"Retrieved non-existent setting: '{non_existent}' (Expected: '{default}')")
    
    # Test the save_settings method
    save_result = settings.save_settings()
    print(f"Saved settings: {'Success' if save_result else 'Failed'}")
    
    print("\nTest completed successfully!")
    
except ImportError as e:
    print(f"ERROR: Could not import SettingsManager class: {e}")
except Exception as e:
    print(f"ERROR: {e}") 