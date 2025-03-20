# core/utils/shortcuts.py

from PyQt6.QtGui import QKeySequence
from PyQt6.QtCore import Qt

class ShortcutManager:
    """
    Manager for keyboard shortcuts throughout the application.
    Centralizes shortcut definitions and provides a consistent API.
    """
    
    # Document Navigation
    NEXT_PAGE = QKeySequence(Qt.Key.Key_PageDown)
    PREV_PAGE = QKeySequence(Qt.Key.Key_PageUp)
    FIRST_PAGE = QKeySequence("Home")
    LAST_PAGE = QKeySequence("End")
    
    # Document Viewing
    ZOOM_IN = QKeySequence(Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Plus)
    ZOOM_OUT = QKeySequence(Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Minus)
    ZOOM_RESET = QKeySequence(Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_0)
    
    # Knowledge Extraction
    CREATE_EXTRACT = QKeySequence("Ctrl+E")
    ADD_BOOKMARK = QKeySequence("Ctrl+B")
    HIGHLIGHT = QKeySequence("Ctrl+H")
    
    # Learning Items
    NEW_LEARNING_ITEM = QKeySequence("Ctrl+L")
    GENERATE_ITEMS = QKeySequence("Ctrl+G")
    
    # Item Priorities
    PRIORITY_INCREASE = QKeySequence("Alt+Up")
    PRIORITY_DECREASE = QKeySequence("Alt+Down")
    PRIORITY_MAX = QKeySequence("Alt+PgUp")
    PRIORITY_MIN = QKeySequence("Alt+PgDown")
    
    # Learning/Review
    START_REVIEW = QKeySequence("Ctrl+R")
    GRADE_0 = QKeySequence("1")
    GRADE_1 = QKeySequence("2")
    GRADE_2 = QKeySequence("3")
    GRADE_3 = QKeySequence("4")
    GRADE_4 = QKeySequence("5")
    GRADE_5 = QKeySequence("6")
    SHOW_ANSWER = QKeySequence("Space")
    
    # Queue Navigation
    NEXT_DOCUMENT = QKeySequence("Alt+Right")
    PREV_DOCUMENT = QKeySequence("Alt+Left")
    
    # Simple Queue Navigation (easier to use)
    QUEUE_NEXT = QKeySequence("N")
    QUEUE_PREV = QKeySequence("P")
    
    # Queue Rating Shortcuts (direct access)
    QUEUE_RATE_1 = QKeySequence("1")  # Hard/Forgot
    QUEUE_RATE_2 = QKeySequence("2")  # Difficult
    QUEUE_RATE_3 = QKeySequence("3")  # Good
    QUEUE_RATE_4 = QKeySequence("4")  # Easy
    QUEUE_RATE_5 = QKeySequence("5")  # Very Easy
    
    # Navigation
    NEXT_TAB = QKeySequence("Ctrl+Tab")
    PREV_TAB = QKeySequence("Ctrl+Shift+Tab")
    CLOSE_TAB = QKeySequence("Ctrl+W")
    
    # Panels
    TOGGLE_CATEGORY_PANEL = QKeySequence("F3")
    TOGGLE_SEARCH_PANEL = QKeySequence("F4")
    TOGGLE_STATS_PANEL = QKeySequence("F5")
    TOGGLE_QUEUE_PANEL = QKeySequence("F6")
    
    # File Operations
    SAVE = QKeySequence("Ctrl+S")
    IMPORT_FILE = QKeySequence("Ctrl+O")
    IMPORT_URL = QKeySequence("Ctrl+U")
    
    # Search and Find
    SEARCH = QKeySequence("Ctrl+F")
    FIND_NEXT = QKeySequence("F3")
    
    # General
    SETTINGS = QKeySequence("Ctrl+,")
    HELP = QKeySequence("F1")
    
    @staticmethod
    def get_shortcut_descriptions():
        """Get a dictionary of shortcut descriptions for the help screen."""
        return {
            "Document Navigation": [
                {"key": "Page Down", "description": "Next page"},
                {"key": "Page Up", "description": "Previous page"},
                {"key": "Home", "description": "First page"},
                {"key": "End", "description": "Last page"},
                {"key": "Ctrl++", "description": "Zoom in"},
                {"key": "Ctrl+-", "description": "Zoom out"},
                {"key": "Ctrl+0", "description": "Reset zoom"}
            ],
            "Knowledge Extraction": [
                {"key": "Ctrl+E", "description": "Create extract from selection"},
                {"key": "Ctrl+B", "description": "Add bookmark at current location"},
                {"key": "Ctrl+H", "description": "Highlight selected text"}
            ],
            "Learning Items": [
                {"key": "Ctrl+L", "description": "Create new learning item"},
                {"key": "Ctrl+G", "description": "Generate learning items automatically"},
                {"key": "Alt+↑", "description": "Increase priority"},
                {"key": "Alt+↓", "description": "Decrease priority"}
            ],
            "Learning & Review": [
                {"key": "Ctrl+R", "description": "Start review session"},
                {"key": "Space", "description": "Show answer during review"},
                {"key": "1-6", "description": "Grade item during review (1=worst, 6=best)"}
            ],
            "Queue Navigation": [
                {"key": "Alt+Right", "description": "Next document in queue"},
                {"key": "Alt+Left", "description": "Previous document in queue"},
                {"key": "N", "description": "Next document in queue (quick key)"},
                {"key": "P", "description": "Previous document in queue (quick key)"},
                {"key": "1", "description": "Rate document as Hard/Forgot"},
                {"key": "2", "description": "Rate document as Difficult"},
                {"key": "3", "description": "Rate document as Good"},
                {"key": "4", "description": "Rate document as Easy"},
                {"key": "5", "description": "Rate document as Very Easy"}
            ],
            "Navigation": [
                {"key": "Ctrl+Tab", "description": "Next tab"},
                {"key": "Ctrl+Shift+Tab", "description": "Previous tab"},
                {"key": "Ctrl+W", "description": "Close current tab"},
                {"key": "F3", "description": "Toggle category panel"},
                {"key": "F4", "description": "Toggle search panel"},
                {"key": "F5", "description": "Toggle statistics panel"},
                {"key": "F6", "description": "Toggle queue panel"}
            ],
            "File Operations": [
                {"key": "Ctrl+O", "description": "Import file"},
                {"key": "Ctrl+U", "description": "Import from URL"},
                {"key": "Ctrl+S", "description": "Save current item"}
            ],
            "Search": [
                {"key": "Ctrl+F", "description": "Search"},
                {"key": "F3", "description": "Find next"}
            ]
        }
