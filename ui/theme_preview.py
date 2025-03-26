#!/usr/bin/env python3
"""
Theme Preview Application for Incrementum.

This application demonstrates the different themes available in Incrementum
and allows users to preview and select themes.
"""

import sys
import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QLineEdit, QTextEdit, QCheckBox, QRadioButton,
    QComboBox, QListWidget, QTreeWidget, QTreeWidgetItem, QTabWidget,
    QGroupBox, QScrollArea, QSlider, QSpinBox, QProgressBar, QMessageBox,
    QToolBar, QStatusBar
)
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtCore import Qt, pyqtSlot

# Add parent directory to path for imports
parent_dir = str(Path(__file__).resolve().parent.parent)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from core.utils.theme_manager import ThemeManager
from core.utils.settings_manager import SettingsManager


class ThemePreviewWindow(QMainWindow):
    """Main window for theme preview application."""
    
    def __init__(self):
        super().__init__()
        
        # Set up settings manager and theme manager
        self.settings_manager = SettingsManager()
        self.theme_manager = ThemeManager(self.settings_manager)
        
        # Initialize UI
        self.setWindowTitle("Incrementum Theme Preview")
        self.setMinimumSize(1000, 600)
        
        # Create main widget and layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        # Main layout is horizontal with theme selector on left and preview on right
        self.main_layout = QHBoxLayout(self.central_widget)
        
        # Create theme selector and preview area
        self._create_theme_selector()
        self._create_preview_area()
        
        # Set up status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")
        
        # Set up toolbar
        self._create_toolbar()
        
        # Apply initial theme
        self._apply_current_theme()
    
    def _create_toolbar(self):
        """Create toolbar with theme-related actions."""
        self.toolbar = QToolBar("Theme Tools")
        self.addToolBar(self.toolbar)
        
        # Add actions
        self.action_refresh = QAction("Refresh", self)
        self.action_refresh.triggered.connect(self._refresh_themes)
        self.toolbar.addAction(self.action_refresh)
        
        self.action_create = QAction("Create Theme", self)
        self.action_create.triggered.connect(self._create_theme)
        self.toolbar.addAction(self.action_create)
        
        self.action_import = QAction("Import Theme", self)
        self.action_import.triggered.connect(self._import_theme)
        self.toolbar.addAction(self.action_import)
        
        self.action_export = QAction("Export Theme", self)
        self.action_export.triggered.connect(self._export_theme)
        self.toolbar.addAction(self.action_export)
    
    def _create_theme_selector(self):
        """Create the theme selection panel on the left."""
        # Create a group box for theme selection
        theme_group = QGroupBox("Available Themes")
        theme_layout = QVBoxLayout(theme_group)
        
        # Create list widget for themes
        self.theme_list = QListWidget()
        self.theme_list.setMinimumWidth(200)
        theme_layout.addWidget(self.theme_list)
        
        # Add themes to list
        self._populate_theme_list()
        
        # Connect selection change
        self.theme_list.currentItemChanged.connect(self._on_theme_selected)
        
        # Apply button
        self.apply_button = QPushButton("Apply Theme")
        self.apply_button.clicked.connect(self._apply_selected_theme)
        theme_layout.addWidget(self.apply_button)
        
        # Add theme selector to main layout
        self.main_layout.addWidget(theme_group, 1)
    
    def _populate_theme_list(self):
        """Populate the theme list with available themes."""
        self.theme_list.clear()
        
        # Add built-in themes
        self.theme_list.addItem("Light")
        self.theme_list.addItem("Dark")
        self.theme_list.addItem("System")
        
        # Add separator
        self.theme_list.addItem("----------- Predefined Themes -----------")
        self.theme_list.item(self.theme_list.count() - 1).setFlags(Qt.ItemFlag.NoItemFlags)
        
        # Add predefined themes
        predefined_themes = [
            "Incrementum",  # Our branded theme
            "Nord", "Solarized Light", "Solarized Dark", "Dracula", "Cyberpunk",
            "Material Light", "Material Dark", "Monokai", "GitHub Light",
            "GitHub Dark", "Pastel"
        ]
        
        for theme in predefined_themes:
            self.theme_list.addItem(theme)
        
        # Add custom themes
        available_themes = self.theme_manager.get_available_themes()
        custom_themes = [t for t in available_themes if t not in ["light", "dark", "system", "nord", 
                                                              "solarized_light", "solarized_dark", 
                                                              "dracula", "cyberpunk", "material_light", 
                                                              "material_dark", "monokai", "github_light", 
                                                              "github_dark", "pastel", "incrementum"]]
        
        if custom_themes:
            # Add separator
            self.theme_list.addItem("----------- Custom Themes -----------")
            self.theme_list.item(self.theme_list.count() - 1).setFlags(Qt.ItemFlag.NoItemFlags)
            
            for theme in custom_themes:
                self.theme_list.addItem(theme.replace('_', ' ').title())
        
        # Set current theme based on settings
        current_theme = self.settings_manager.get_setting("ui", "theme", "light")
        
        # Find and select the current theme in the list
        for i in range(self.theme_list.count()):
            item = self.theme_list.item(i)
            if item.text().lower().replace(' ', '_') == current_theme:
                self.theme_list.setCurrentItem(item)
                break
    
    def _create_preview_area(self):
        """Create the preview area showing various widgets with the theme applied."""
        # Create a scroll area for preview
        preview_scroll = QScrollArea()
        preview_scroll.setWidgetResizable(True)
        
        # Create main preview widget
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        
        # Add header
        header_label = QLabel("Theme Preview")
        header_label.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 10px;")
        preview_layout.addWidget(header_label)
        
        # Create tabs for different categories of widgets
        preview_tabs = QTabWidget()
        
        # Basic widgets tab
        basic_tab = QWidget()
        basic_layout = QVBoxLayout(basic_tab)
        
        # Group box for text controls
        text_group = QGroupBox("Text Controls")
        text_layout = QGridLayout(text_group)
        
        # Add various text controls
        text_layout.addWidget(QLabel("Label:"), 0, 0)
        text_layout.addWidget(QLabel("This is a sample text label"), 0, 1)
        
        text_layout.addWidget(QLabel("LineEdit:"), 1, 0)
        text_layout.addWidget(QLineEdit("Editable text"), 1, 1)
        
        text_layout.addWidget(QLabel("TextEdit:"), 2, 0)
        text_edit = QTextEdit()
        text_edit.setPlainText("This is a multi-line text editor.\nIt supports rich text formatting.")
        text_layout.addWidget(text_edit, 2, 1)
        
        basic_layout.addWidget(text_group)
        
        # Group box for buttons
        button_group = QGroupBox("Button Controls")
        button_layout = QGridLayout(button_group)
        
        # Add various button types
        button_layout.addWidget(QLabel("Push Button:"), 0, 0)
        button_layout.addWidget(QPushButton("Click Me"), 0, 1)
        
        button_layout.addWidget(QLabel("Checkbox:"), 1, 0)
        button_layout.addWidget(QCheckBox("Enable feature"), 1, 1)
        
        button_layout.addWidget(QLabel("Radio Buttons:"), 2, 0)
        radio_layout = QHBoxLayout()
        radio_layout.addWidget(QRadioButton("Option 1"))
        radio_layout.addWidget(QRadioButton("Option 2"))
        radio_layout.addWidget(QRadioButton("Option 3"))
        button_layout.addLayout(radio_layout, 2, 1)
        
        basic_layout.addWidget(button_group)
        
        # Group for selection widgets
        selection_group = QGroupBox("Selection Controls")
        selection_layout = QGridLayout(selection_group)
        
        # Add combo box
        selection_layout.addWidget(QLabel("ComboBox:"), 0, 0)
        combo = QComboBox()
        combo.addItems(["Item 1", "Item 2", "Item 3", "Item 4"])
        selection_layout.addWidget(combo, 0, 1)
        
        # Add list widget
        selection_layout.addWidget(QLabel("ListWidget:"), 1, 0)
        list_widget = QListWidget()
        list_widget.addItems(["Item 1", "Item 2", "Item 3", "Item 4", "Item 5"])
        selection_layout.addWidget(list_widget, 1, 1)
        
        basic_layout.addWidget(selection_group)
        
        # Add the tab
        preview_tabs.addTab(basic_tab, "Basic Widgets")
        
        # Advanced widgets tab
        advanced_tab = QWidget()
        advanced_layout = QVBoxLayout(advanced_tab)
        
        # Tree widget
        tree_group = QGroupBox("Tree Widget")
        tree_layout = QVBoxLayout(tree_group)
        
        tree = QTreeWidget()
        tree.setHeaderLabels(["Column 1", "Column 2", "Column 3"])
        
        # Add items
        for i in range(5):
            parent = QTreeWidgetItem(tree)
            parent.setText(0, f"Parent {i+1}")
            parent.setText(1, f"Value {i+1}")
            parent.setText(2, f"Extra {i+1}")
            
            for j in range(3):
                child = QTreeWidgetItem(parent)
                child.setText(0, f"Child {i+1}.{j+1}")
                child.setText(1, f"Value {i+1}.{j+1}")
                child.setText(2, f"Extra {i+1}.{j+1}")
        
        tree_layout.addWidget(tree)
        advanced_layout.addWidget(tree_group)
        
        # Progress indicators
        progress_group = QGroupBox("Progress Indicators")
        progress_layout = QGridLayout(progress_group)
        
        progress_layout.addWidget(QLabel("Slider:"), 0, 0)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setValue(50)
        progress_layout.addWidget(slider, 0, 1)
        
        progress_layout.addWidget(QLabel("SpinBox:"), 1, 0)
        spin = QSpinBox()
        spin.setValue(50)
        progress_layout.addWidget(spin, 1, 1)
        
        progress_layout.addWidget(QLabel("ProgressBar:"), 2, 0)
        progress = QProgressBar()
        progress.setValue(75)
        progress_layout.addWidget(progress, 2, 1)
        
        advanced_layout.addWidget(progress_group)
        
        # Add the tab
        preview_tabs.addTab(advanced_tab, "Advanced Widgets")
        
        # Add tabs to layout
        preview_layout.addWidget(preview_tabs)
        
        # Set the preview widget
        preview_scroll.setWidget(preview_widget)
        self.main_layout.addWidget(preview_scroll, 3)
        
        # Store theme name label
        self.theme_name_label = header_label
    
    @pyqtSlot()
    def _refresh_themes(self):
        """Refresh the list of available themes."""
        self._populate_theme_list()
        self.status_bar.showMessage("Theme list refreshed", 3000)
    
    @pyqtSlot()
    def _create_theme(self):
        """Create a new theme template."""
        from PyQt6.QtWidgets import QFileDialog
        
        # Ask for file name and location
        file_dialog = QFileDialog(self)
        file_dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        file_dialog.setNameFilter("Theme Files (*.json)")
        file_dialog.setDefaultSuffix("json")
        
        if file_dialog.exec():
            file_path = file_dialog.selectedFiles()[0]
            if file_path:
                # Create the theme template
                success = self.theme_manager.create_theme_template(file_path)
                
                if success:
                    self.status_bar.showMessage(f"Theme template created at {file_path}", 5000)
                    
                    # Refresh theme list
                    self._refresh_themes()
                else:
                    QMessageBox.warning(
                        self, "Error", 
                        f"Failed to create theme template at {file_path}."
                    )
    
    @pyqtSlot()
    def _import_theme(self):
        """Import a theme from a file."""
        from PyQt6.QtWidgets import QFileDialog
        import shutil
        
        # Ask for theme file
        file_dialog = QFileDialog(self)
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        file_dialog.setNameFilter("Theme Files (*.json *.qss)")
        
        if file_dialog.exec():
            file_path = file_dialog.selectedFiles()[0]
            if file_path:
                # Get the theme name from file
                theme_name = os.path.basename(file_path).split('.')[0]
                
                # Copy to theme directory                    
                theme_dir = self.theme_manager._get_theme_directory()
                theme_dir.mkdir(parents=True, exist_ok=True)
                
                if file_path.endswith('.json'):
                    dest_path = theme_dir / f"{theme_name}.json"
                else:
                    dest_path = theme_dir / f"{theme_name}.qss"
                
                try:
                    shutil.copy2(file_path, dest_path)
                    self.status_bar.showMessage(f"Theme imported successfully: {theme_name}", 5000)
                    
                    # Refresh theme list
                    self._refresh_themes()
                    
                except Exception as e:
                    QMessageBox.warning(
                        self, "Import Error", 
                        f"Failed to import theme: {str(e)}"
                    )
    
    @pyqtSlot()
    def _export_theme(self):
        """Export the current theme to a file."""
        from PyQt6.QtWidgets import QFileDialog
        
        # Get current theme name
        current_item = self.theme_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Error", "No theme selected to export.")
            return
        
        theme_name = current_item.text().lower().replace(' ', '_')
        
        # Ask for export location
        file_dialog = QFileDialog(self)
        file_dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        file_dialog.setNameFilter("Theme Files (*.json)")
        file_dialog.setDefaultSuffix("json")
        file_dialog.selectFile(f"{theme_name}_exported.json")
        
        if file_dialog.exec():
            file_path = file_dialog.selectedFiles()[0]
            if file_path:
                # Get theme path
                theme_path = self.theme_manager.get_theme_path(theme_name)
                
                if theme_path:
                    try:
                        import shutil
                        shutil.copy2(theme_path, file_path)
                        self.status_bar.showMessage(f"Theme exported to {file_path}", 5000)
                    except Exception as e:
                        QMessageBox.warning(
                            self, "Export Error", 
                            f"Failed to export theme: {str(e)}"
                        )
                else:
                    # Try to export current theme
                    success = self.theme_manager.export_current_theme(file_path)
                    if success:
                        self.status_bar.showMessage(f"Theme exported to {file_path}", 5000)
                    else:
                        QMessageBox.warning(
                            self, "Export Error", 
                            "Failed to export theme."
                        )
    
    @pyqtSlot(QListWidget.currentItemChanged)
    def _on_theme_selected(self, current, previous):
        """Handle theme selection change in the list."""
        if current:
            theme_name = current.text()
            self.theme_name_label.setText(f"Theme Preview: {theme_name}")
    
    @pyqtSlot()
    def _apply_selected_theme(self):
        """Apply the selected theme."""
        current_item = self.theme_list.currentItem()
        if not current_item:
            return
        
        # Get theme name (convert display name to internal name)
        theme_name = current_item.text().lower().replace(' ', '_')
        
        # Skip separator items
        if theme_name.startswith('-'):
            return
        
        # Update settings
        self.settings_manager.set_setting("ui", "theme", theme_name)
        self.settings_manager.set_setting("ui", "custom_theme", False)
        
        # Apply theme
        self._apply_current_theme()
        
        # Update status
        self.status_bar.showMessage(f"Theme applied: {current_item.text()}", 3000)
    
    def _apply_current_theme(self):
        """Apply the current theme from settings."""
        # Get current theme from settings
        current_theme = self.settings_manager.get_setting("ui", "theme", "light")
        
        # Apply to application
        app = QApplication.instance()
        if app:
            self.theme_manager.apply_theme(app, current_theme)
            
            # Update theme name in header
            # Find the display name for the current theme
            for i in range(self.theme_list.count()):
                item = self.theme_list.item(i)
                if item.text().lower().replace(' ', '_') == current_theme:
                    self.theme_name_label.setText(f"Theme Preview: {item.text()}")
                    break


def main():
    """Main entry point for the theme preview application."""
    app = QApplication(sys.argv)
    
    window = ThemePreviewWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main() 