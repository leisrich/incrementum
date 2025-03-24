from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QFrame, QSpacerItem, QSizePolicy)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QPixmap

class WelcomeScreen(QWidget):
    """A modern welcome screen for Incrementum showing stats and quick actions."""
    
    # Signals
    quick_add_document_clicked = pyqtSignal()
    start_review_clicked = pyqtSignal()
    browse_documents_clicked = pyqtSignal()
    view_statistics_clicked = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()
        
    def initUI(self):
        """Initialize the UI components."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)
        
        # Welcome header
        header_layout = QHBoxLayout()
        
        # App logo (placeholder - would be replaced with actual logo)
        logo_label = QLabel()
        logo_label.setFixedSize(64, 64)
        # logo_label.setPixmap(QPixmap(":/icons/app_logo.png").scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio))
        header_layout.addWidget(logo_label)
        
        # Welcome text
        welcome_label = QLabel("Welcome to Incrementum")
        welcome_label.setObjectName("welcomeMessage")
        welcome_label.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        header_layout.addWidget(welcome_label)
        header_layout.addStretch()
        
        main_layout.addLayout(header_layout)
        
        # Horizontal separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setObjectName("separator")
        main_layout.addWidget(separator)
        
        # Main content area with stats and quick actions
        content_layout = QHBoxLayout()
        content_layout.setSpacing(20)
        
        # Left side - Statistics
        stats_frame = QFrame()
        stats_frame.setObjectName("statsFrame")
        stats_frame.setFrameShape(QFrame.Shape.NoFrame)
        
        stats_layout = QVBoxLayout(stats_frame)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        
        stats_title = QLabel("Your Learning Statistics")
        stats_title.setObjectName("sectionTitle")
        stats_title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        stats_layout.addWidget(stats_title)
        
        # Stats cards
        stats_layout.addWidget(self._create_stat_card("Today's Queue", "12", "Items scheduled for today"))
        stats_layout.addWidget(self._create_stat_card("Retention Rate", "87%", "Your overall retention rate"))
        stats_layout.addWidget(self._create_stat_card("Learning Streak", "7 days", "Keep up the good work!"))
        stats_layout.addWidget(self._create_stat_card("Total Documents", "34", "Documents in your collection"))
        
        stats_layout.addStretch()
        content_layout.addWidget(stats_frame, 1)
        
        # Right side - Quick Actions
        actions_frame = QFrame()
        actions_frame.setObjectName("actionsFrame")
        actions_frame.setFrameShape(QFrame.Shape.NoFrame)
        
        actions_layout = QVBoxLayout(actions_frame)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        
        actions_title = QLabel("Quick Actions")
        actions_title.setObjectName("sectionTitle")
        actions_title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        actions_layout.addWidget(actions_title)
        
        # Quick action buttons
        add_doc_btn = self._create_action_button(
            "Add New Document", 
            "Import a new document into your collection",
            "document-add"
        )
        add_doc_btn.clicked.connect(self.quick_add_document_clicked.emit)
        actions_layout.addWidget(add_doc_btn)
        
        review_btn = self._create_action_button(
            "Start Review Session", 
            "Begin reviewing your scheduled items",
            "review"
        )
        review_btn.clicked.connect(self.start_review_clicked.emit)
        actions_layout.addWidget(review_btn)
        
        browse_btn = self._create_action_button(
            "Browse Documents", 
            "View and manage your document collection",
            "browse"
        )
        browse_btn.clicked.connect(self.browse_documents_clicked.emit)
        actions_layout.addWidget(browse_btn)
        
        stats_btn = self._create_action_button(
            "View Detailed Statistics", 
            "See comprehensive learning analytics",
            "statistics"
        )
        stats_btn.clicked.connect(self.view_statistics_clicked.emit)
        actions_layout.addWidget(stats_btn)
        
        actions_layout.addStretch()
        content_layout.addWidget(actions_frame, 1)
        
        main_layout.addLayout(content_layout)
        
        # Tips section at bottom
        tip_frame = QFrame()
        tip_frame.setObjectName("tipFrame")
        tip_layout = QHBoxLayout(tip_frame)
        
        tip_icon = QLabel()
        tip_icon.setFixedSize(32, 32)
        # tip_icon.setPixmap(QPixmap(":/icons/tip.png").scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio))
        tip_layout.addWidget(tip_icon)
        
        tip_text = QLabel("Tip: Use keyboard shortcuts to speed up your review sessions. Press '?' to see all shortcuts.")
        tip_text.setObjectName("tipText")
        tip_layout.addWidget(tip_text)
        
        main_layout.addWidget(tip_frame)
        
    def _create_stat_card(self, title, value, description):
        """Create a statistics card widget."""
        card = QFrame()
        card.setObjectName("statCard")
        card.setProperty("class", "stats-card")
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        
        title_label = QLabel(title)
        title_label.setObjectName("statTitle")
        title_label.setProperty("class", "stats-header")
        layout.addWidget(title_label)
        
        value_label = QLabel(value)
        value_label.setObjectName("statValue")
        value_label.setProperty("class", "stats-value")
        layout.addWidget(value_label)
        
        desc_label = QLabel(description)
        desc_label.setObjectName("statDescription")
        desc_label.setProperty("class", "stats-description")
        layout.addWidget(desc_label)
        
        return card
    
    def _create_action_button(self, title, description, icon_name):
        """Create a quick action button."""
        button = QPushButton()
        button.setObjectName(f"{icon_name}Button")
        button.setProperty("class", "feature-card card-hover")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumHeight(80)
        
        layout = QHBoxLayout(button)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # Icon (placeholder - would use actual icons)
        icon_label = QLabel()
        icon_label.setFixedSize(32, 32)
        # icon_label.setPixmap(QPixmap(f":/icons/{icon_name}.png").scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio))
        layout.addWidget(icon_label)
        
        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)
        
        title_label = QLabel(title)
        title_label.setObjectName("actionTitle")
        title_label.setProperty("class", "feature-title")
        text_layout.addWidget(title_label)
        
        desc_label = QLabel(description)
        desc_label.setObjectName("actionDescription")
        desc_label.setProperty("class", "feature-description")
        text_layout.addWidget(desc_label)
        
        layout.addLayout(text_layout)
        layout.addStretch()
        
        return button
    
    def set_stats(self, today_queue=0, retention_rate=0, streak=0, total_docs=0):
        """Update the statistics displayed on the welcome screen."""
        # This method would be called to update the statistics with real data
        pass

    def set_tip(self, tip_text):
        """Update the tip shown at the bottom of the screen."""
        # This method would update the tip text
        pass 