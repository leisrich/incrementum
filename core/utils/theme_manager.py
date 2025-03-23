"""
Theme manager for Incrementum application.
Handles theme switching, dark mode, and custom theme loading.
"""

import os
import json
import logging
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtCore import QFile, QTextStream

logger = logging.getLogger(__name__)

class ThemeManager:
    """
    Manages application themes including light mode, dark mode, and custom themes.
    Provides methods to apply themes to the application.
    """
    
    # Default theme colors (light theme)
    DEFAULT_LIGHT_COLORS = {
        "window": "#FFFFFF",
        "windowText": "#000000",
        "base": "#FFFFFF",
        "alternateBase": "#F2F2F2",
        "text": "#000000",
        "button": "#E0E0E0",
        "buttonText": "#000000",
        "brightText": "#FFFFFF",
        "highlight": "#308CC6",
        "highlightedText": "#FFFFFF",
        "link": "#0000FF",
        "midLight": "#E3E3E3",
        "dark": "#A0A0A0",
        "mid": "#B8B8B8",
        "shadow": "#505050",
        "light": "#FFFFFF"
    }
    
    # Default dark theme colors
    DEFAULT_DARK_COLORS = {
        "window": "#2D2D30",
        "windowText": "#FFFFFF",
        "base": "#252526",
        "alternateBase": "#3C3C3C",
        "text": "#FFFFFF",
        "button": "#3C3C3C",
        "buttonText": "#FFFFFF",
        "brightText": "#FFFFFF",
        "highlight": "#264F78",
        "highlightedText": "#FFFFFF",
        "link": "#4EB8FF",
        "midLight": "#3C3C3C",
        "dark": "#1E1E1E",
        "mid": "#2D2D30",
        "shadow": "#1A1A1A",
        "light": "#505050"
    }
    
    def __init__(self, settings_manager=None):
        """
        Initialize the theme manager.
        
        Args:
            settings_manager: Optional settings manager to retrieve theme settings
        """
        self.settings_manager = settings_manager
        self.current_theme = "light"
        self.custom_theme_path = None
        
        # Create theme directory if it doesn't exist
        self.theme_dir = self._get_theme_directory()
        self.theme_dir.mkdir(parents=True, exist_ok=True)
        
        # Create default themes if they don't exist
        self._create_default_themes()
        
    def _get_theme_directory(self) -> Path:
        """
        Get or create the theme directory.
        
        Returns:
            Path object to the theme directory
        """
        # Use user's home directory + .incrementum/themes
        return Path.home() / ".incrementum" / "themes"
    
    def _create_default_themes(self):
        """Create default theme files if they don't exist."""
        # Create light theme
        light_theme_path = self.theme_dir / "light.json"
        if not light_theme_path.exists():
            with open(light_theme_path, 'w', encoding='utf-8') as f:
                json.dump(self.DEFAULT_LIGHT_COLORS, f, indent=4)
                
        # Create dark theme
        dark_theme_path = self.theme_dir / "dark.json"
        if not dark_theme_path.exists():
            with open(dark_theme_path, 'w', encoding='utf-8') as f:
                json.dump(self.DEFAULT_DARK_COLORS, f, indent=4)
    
    def get_available_themes(self) -> list:
        """
        Get a list of available themes.
        
        Returns:
            List of theme names
        """
        themes = ["light", "dark"]
        
        # Add custom themes from the theme directory
        if self.theme_dir.exists():
            for file in self.theme_dir.glob("*.json"):
                theme_name = file.stem
                if theme_name not in themes:
                    themes.append(theme_name)
                    
        return themes
    
    def _load_theme_from_file(self, theme_path: str) -> dict:
        """
        Load a theme from a file.
        
        Args:
            theme_path: Path to the theme file
            
        Returns:
            Dictionary of theme colors or None if file not found
        """
        try:
            with open(theme_path, 'r', encoding='utf-8') as f:
                theme_data = json.load(f)
            return theme_data
        except Exception as e:
            logger.error(f"Error loading theme from {theme_path}: {e}")
            return None
    
    def _load_qss_from_file(self, qss_path: str) -> str:
        """
        Load a QSS style sheet from a file.
        
        Args:
            qss_path: Path to the QSS file
            
        Returns:
            QSS content as string
        """
        try:
            with open(qss_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error loading QSS from {qss_path}: {e}")
            return ""
    
    def apply_theme(self, app: QApplication, theme_name: str = None, custom_theme_path: str = None):
        """
        Apply a theme to the application.
        
        Args:
            app: QApplication instance
            theme_name: Name of the theme (light, dark, system, or custom)
            custom_theme_path: Path to a custom theme file
            
        Returns:
            bool: True if theme was successfully applied, False otherwise
        """
        try:
            # Get theme from settings if not specified
            if theme_name is None and self.settings_manager:
                theme_name = self.settings_manager.get_setting("ui", "theme", "light")
                logger.debug(f"No theme_name provided, using from settings: {theme_name}")
            else:
                logger.debug(f"Using provided theme_name: {theme_name}")
                
            # Check for dark mode setting if using built-in dark mode
            if theme_name == "dark" or (self.settings_manager and 
                                       self.settings_manager.get_setting("ui", "dark_mode", False)):
                theme_name = "dark"
                logger.debug("Using dark theme due to dark_mode setting")
                
            # Check for custom theme
            use_custom_theme = self.settings_manager and self.settings_manager.get_setting("ui", "custom_theme", False)
            logger.debug(f"Custom theme enabled in settings: {use_custom_theme}")
            
            if use_custom_theme:
                if custom_theme_path is None and self.settings_manager:
                    custom_theme_path = self.settings_manager.get_setting("ui", "theme_file", "")
                    logger.debug(f"Using custom theme path from settings: {custom_theme_path}")
                else:
                    logger.debug(f"Using provided custom theme path: {custom_theme_path}")
                    
                if custom_theme_path and os.path.exists(custom_theme_path):
                    logger.debug(f"Applying custom theme from: {custom_theme_path}")
                    success = self._apply_custom_theme(app, custom_theme_path)
                    self.current_theme = "custom"
                    self.custom_theme_path = custom_theme_path
                    return success
                else:
                    logger.warning(f"Custom theme path not found: {custom_theme_path}")
                    
            # Apply built-in theme
            logger.debug(f"Applying built-in theme: {theme_name}")
            if theme_name == "dark":
                self._apply_dark_theme(app)
                self.current_theme = "dark"
            elif theme_name == "system":
                self._apply_system_theme(app)
                self.current_theme = "system"
            else:
                self._apply_light_theme(app)
                self.current_theme = "light"
                
            return True
            
        except Exception as e:
            logger.error(f"Error applying theme: {e}")
            return False
    
    def _apply_dark_theme(self, app: QApplication):
        """
        Apply dark theme to the application.
        
        Args:
            app: QApplication instance
            
        Returns:
            bool: True if theme was successfully applied
        """
        # Load the dark theme file
        theme_path = self.theme_dir / "dark.json"
        if theme_path.exists():
            theme_data = self._load_theme_from_file(str(theme_path))
            if theme_data:
                self._apply_palette_colors(app, theme_data)
                logger.info("Applied dark theme from file")
                return True
        
        # Fallback to default dark theme
        self._apply_palette_colors(app, self.DEFAULT_DARK_COLORS)
        logger.info("Applied default dark theme")
        
        # Also apply dark mode stylesheet
        qss_path = self.theme_dir / "dark.qss"
        if qss_path.exists():
            qss = self._load_qss_from_file(str(qss_path))
            app.setStyleSheet(qss)
            
        return True
    
    def _apply_light_theme(self, app: QApplication):
        """
        Apply light theme to the application.
        
        Args:
            app: QApplication instance
            
        Returns:
            bool: True if theme was successfully applied
        """
        # Load the light theme file
        theme_path = self.theme_dir / "light.json"
        if theme_path.exists():
            theme_data = self._load_theme_from_file(str(theme_path))
            if theme_data:
                self._apply_palette_colors(app, theme_data)
                logger.info("Applied light theme from file")
                return True
                
        # Fallback to default light theme
        self._apply_palette_colors(app, self.DEFAULT_LIGHT_COLORS)
        logger.info("Applied default light theme")
        
        # Also apply light mode stylesheet
        qss_path = self.theme_dir / "light.qss"
        if qss_path.exists():
            qss = self._load_qss_from_file(str(qss_path))
            app.setStyleSheet(qss)
        
        return True
    
    def _apply_system_theme(self, app: QApplication):
        """
        Apply system theme to the application.
        
        Args:
            app: QApplication instance
            
        Returns:
            bool: True if theme was successfully applied
        """
        # Reset to system style
        app.setStyle(app.style().objectName())
        app.setPalette(app.style().standardPalette())
        app.setStyleSheet("")
        logger.info("Applied system theme")
        return True
    
    def _apply_custom_theme(self, app: QApplication, theme_path: str):
        """
        Apply a custom theme to the application.
        
        Args:
            app: QApplication instance
            theme_path: Path to the custom theme file
        """
        # Check for JSON theme file
        if theme_path.lower().endswith('.json'):
            theme_data = self._load_theme_from_file(theme_path)
            if theme_data:
                self._apply_palette_colors(app, theme_data)
                logger.info(f"Applied custom theme from {theme_path}")
                
                # Check for matching QSS file
                qss_path = os.path.splitext(theme_path)[0] + '.qss'
                if os.path.exists(qss_path):
                    qss = self._load_qss_from_file(qss_path)
                    app.setStyleSheet(qss)
                    
                return True
        
        # Check for QSS theme file
        elif theme_path.lower().endswith('.qss'):
            qss = self._load_qss_from_file(theme_path)
            app.setStyleSheet(qss)
            logger.info(f"Applied custom QSS theme from {theme_path}")
            return True
            
        # If we got here, the theme couldn't be applied
        logger.error(f"Failed to apply custom theme from {theme_path}")
        return False
        
    def _apply_palette_colors(self, app: QApplication, colors: dict):
        """
        Apply palette colors to the application.
        
        Args:
            app: QApplication instance
            colors: Dictionary of color values by palette role
        """
        # Create a new palette based on the current one
        palette = app.palette()
        
        # Map of color name to QPalette color role
        role_map = {
            "window": QPalette.ColorRole.Window,
            "windowText": QPalette.ColorRole.WindowText,
            "base": QPalette.ColorRole.Base,
            "alternateBase": QPalette.ColorRole.AlternateBase,
            "text": QPalette.ColorRole.Text,
            "button": QPalette.ColorRole.Button,
            "buttonText": QPalette.ColorRole.ButtonText,
            "brightText": QPalette.ColorRole.BrightText,
            "highlight": QPalette.ColorRole.Highlight,
            "highlightedText": QPalette.ColorRole.HighlightedText,
            "link": QPalette.ColorRole.Link,
            "midLight": QPalette.ColorRole.Midlight,
            "dark": QPalette.ColorRole.Dark,
            "mid": QPalette.ColorRole.Mid,
            "shadow": QPalette.ColorRole.Shadow,
            "light": QPalette.ColorRole.Light
        }
        
        # Apply colors to palette
        for name, role in role_map.items():
            if name in colors:
                color = QColor(colors[name])
                palette.setColor(role, color)
                # Also set inactive and disabled states
                palette.setColor(QPalette.ColorGroup.Inactive, role, color)
                # For disabled group, adjust brightness for some roles
                if role in [QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText]:
                    palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#808080"))
                else:
                    palette.setColor(QPalette.ColorGroup.Disabled, role, color)
        
        # Apply palette to application
        app.setPalette(palette)
        
    def export_current_theme(self, output_path: str) -> bool:
        """
        Export the current theme to a file.
        
        Args:
            output_path: Path to save the theme file
            
        Returns:
            True if successful, False if failed
        """
        try:
            # If using a custom theme, copy it
            if self.current_theme == "custom" and self.custom_theme_path:
                with open(self.custom_theme_path, 'r', encoding='utf-8') as src:
                    with open(output_path, 'w', encoding='utf-8') as dst:
                        dst.write(src.read())
            else:
                # Otherwise export the current theme
                if self.current_theme == "dark":
                    theme_data = self.DEFAULT_DARK_COLORS
                else:
                    theme_data = self.DEFAULT_LIGHT_COLORS
                    
                # Write to file
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(theme_data, f, indent=4)
                    
            logger.info(f"Exported current theme to {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error exporting theme to {output_path}: {e}")
            return False
            
    def get_theme_path(self, theme_name):
        """
        Get the path to a theme file by name.
        
        Args:
            theme_name (str): The name of the theme to find
            
        Returns:
            str: Path to the theme file, or None if not found
        """
        try:
            # First check in themes directory for a JSON file
            theme_path = self.theme_dir / f"{theme_name}.json"
            if theme_path.exists():
                logger.debug(f"Found theme at: {theme_path}")
                return str(theme_path)
                
            # Check for QSS file
            qss_path = self.theme_dir / f"{theme_name}.qss"
            if qss_path.exists():
                logger.debug(f"Found QSS theme at: {qss_path}")
                return str(qss_path)
                
            # If it's a built-in theme, return its path
            if theme_name in ["light", "dark"]:
                built_in_path = self.theme_dir / f"{theme_name}.json"
                if built_in_path.exists():
                    logger.debug(f"Using built-in theme: {built_in_path}")
                    return str(built_in_path)
                
            logger.warning(f"Could not find theme path for: {theme_name}")
            return None
        except Exception as e:
            logger.error(f"Error getting theme path: {e}")
            return None
            
    def create_theme_template(self, file_path):
        """
        Create a new theme template at the specified location.
        
        Args:
            file_path (str): Path where the theme template should be saved
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create a template with light theme colors as a starting point
            template = {
                "name": "Custom Theme",
                "description": "My custom theme for Incrementum",
                "created": datetime.now().isoformat(),
                "colors": self.DEFAULT_LIGHT_COLORS.copy()
            }
            
            # Add some extra documentation in the template
            template["documentation"] = {
                "usage": "Edit the color values to customize your theme.",
                "format": "Use standard color names, hex values (#RRGGBB or #AARRGGBB), or rgb/rgba values."
            }
            
            # Write the template to file
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(template, f, indent=2)
                
            # Copy the file to themes directory if it's not already there
            theme_name = Path(file_path).stem
            theme_copy_path = self.theme_dir / f"{theme_name}.json"
            
            if str(theme_copy_path) != file_path:
                self.theme_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy(file_path, theme_copy_path)
                
            return True
        except Exception as e:
            logger.error(f"Error creating theme template: {e}")
            return False 