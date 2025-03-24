# ui/review_widget.py

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QProgressBar, QStackedWidget, QTextEdit, QGroupBox, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QSize
from PyQt6.QtGui import QFont

from core.knowledge_base.models import LearningItem, ReviewLog
from core.spaced_repetition.fsrs import FSRSAlgorithm

logger = logging.getLogger(__name__)

class ReviewWidget(QWidget):
    """Widget for reviewing learning items."""
    
    reviewCompleted = pyqtSignal()  # Emitted when all items are reviewed
    itemReviewed = pyqtSignal(int, int)  # Emitted when an item is reviewed (item_id, rating)
    
    def __init__(self, db_session, items: List[LearningItem] = None):
        super().__init__()
        
        self.db_session = db_session
        self.fsrs = FSRSAlgorithm(db_session)
        
        # Learning items to review
        self.items = items or []
        self.current_item_index = -1
        self.current_item = None
        
        # Track review progress
        self.items_reviewed = 0
        self.total_items = len(self.items)
        
        # Answer revealed flag
        self.answer_revealed = False
        
        # Create UI
        self._create_ui()
        
        # Start review if items provided
        if self.items:
            self._next_item()
    
    def _create_ui(self):
        """Create the review UI."""
        main_layout = QVBoxLayout(self)
        
        # Progress indicators
        progress_layout = QHBoxLayout()
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, max(1, len(self.items)))
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)
        
        # Progress label
        self.progress_label = QLabel("0 / 0")
        progress_layout.addWidget(self.progress_label)
        
        main_layout.addLayout(progress_layout)
        
        # Review content area
        self.content_stack = QStackedWidget()
        
        # Card view
        self.card_widget = QWidget()
        card_layout = QVBoxLayout(self.card_widget)
        
        # Question group
        question_group = QGroupBox("Question")
        question_layout = QVBoxLayout(question_group)
        
        self.question_display = QTextEdit()
        self.question_display.setReadOnly(True)
        self.question_display.setMinimumHeight(150)
        question_layout.addWidget(self.question_display)
        
        card_layout.addWidget(question_group)
        
        # Answer group
        answer_group = QGroupBox("Answer")
        answer_layout = QVBoxLayout(answer_group)
        
        self.answer_display = QTextEdit()
        self.answer_display.setReadOnly(True)
        self.answer_display.setMinimumHeight(150)
        answer_layout.addWidget(self.answer_display)
        
        card_layout.addWidget(answer_group)
        
        # Metadata
        meta_layout = QHBoxLayout()
        self.item_type_label = QLabel("Type: ")
        meta_layout.addWidget(self.item_type_label)
        
        meta_layout.addStretch()
        
        self.extract_info_label = QLabel("Extract: ")
        meta_layout.addWidget(self.extract_info_label)
        
        card_layout.addLayout(meta_layout)
        
        self.content_stack.addWidget(self.card_widget)
        
        # Completed view
        self.completed_widget = QWidget()
        completed_layout = QVBoxLayout(self.completed_widget)
        
        completed_label = QLabel("Review session completed!")
        completed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPointSize(16)
        completed_label.setFont(font)
        completed_layout.addWidget(completed_label)
        
        self.stats_label = QLabel("Items reviewed: 0")
        self.stats_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        completed_layout.addWidget(self.stats_label)
        
        self.content_stack.addWidget(self.completed_widget)
        
        main_layout.addWidget(self.content_stack)
        
        # Control buttons
        self.controls_layout = QHBoxLayout()
        
        # Show answer button
        self.show_answer_button = QPushButton("Show Answer")
        self.show_answer_button.clicked.connect(self._show_answer)
        self.controls_layout.addWidget(self.show_answer_button)
        
        # Rating buttons
        self.rating_frame = QFrame()
        self.rating_layout = QHBoxLayout(self.rating_frame)
        
        self.again_button = QPushButton("Again (1)")
        self.again_button.clicked.connect(lambda: self._rate_item(1))
        self.rating_layout.addWidget(self.again_button)
        
        self.hard_button = QPushButton("Hard (2)")
        self.hard_button.clicked.connect(lambda: self._rate_item(2))
        self.rating_layout.addWidget(self.hard_button)
        
        self.good_button = QPushButton("Good (3)")
        self.good_button.clicked.connect(lambda: self._rate_item(3))
        self.rating_layout.addWidget(self.good_button)
        
        self.easy_button = QPushButton("Easy (4)")
        self.easy_button.clicked.connect(lambda: self._rate_item(4))
        self.rating_layout.addWidget(self.easy_button)
        
        self.rating_frame.setVisible(False)
        self.controls_layout.addWidget(self.rating_frame)
        
        # Done button (shown when review is complete)
        self.done_button = QPushButton("Done")
        self.done_button.clicked.connect(self.reviewCompleted.emit)
        self.done_button.setVisible(False)
        self.controls_layout.addWidget(self.done_button)
        
        main_layout.addLayout(self.controls_layout)
    
    def _update_progress(self):
        """Update the progress indicators."""
        self.progress_bar.setValue(self.items_reviewed)
        self.progress_label.setText(f"{self.items_reviewed} / {self.total_items}")
    
    def _next_item(self):
        """Show the next item for review."""
        # Reset state
        self.answer_revealed = False
        self.show_answer_button.setVisible(True)
        self.rating_frame.setVisible(False)
        
        # Check if we have more items
        if self.current_item_index + 1 < len(self.items):
            # Move to next item
            self.current_item_index += 1
            self.current_item = self.items[self.current_item_index]
            
            # Update display
            self._display_current_item()
        else:
            # No more items, show completed screen
            self._show_completed()
    
    def _display_current_item(self):
        """Display the current item."""
        if not self.current_item:
            return
        
        # Set question text
        self.question_display.setHtml(f"<div style='font-size: 14pt;'>{self.current_item.question}</div>")
        
        # Clear answer text
        self.answer_display.clear()
        
        # Set metadata
        self.item_type_label.setText(f"Type: {self.current_item.item_type}")
        
        # Set extract info if available
        extract_text = "Extract: "
        if self.current_item.extract:
            extract_content = self.current_item.extract.content
            if len(extract_content) > 30:
                extract_content = extract_content[:27] + "..."
            extract_text += extract_content
        else:
            extract_text += "Unknown"
        self.extract_info_label.setText(extract_text)
    
    def _show_answer(self):
        """Reveal the answer."""
        if not self.current_item:
            return
        
        # Display answer
        self.answer_display.setHtml(f"<div style='font-size: 14pt;'>{self.current_item.answer}</div>")
        
        # Update UI
        self.answer_revealed = True
        self.show_answer_button.setVisible(False)
        self.rating_frame.setVisible(True)
    
    def _rate_item(self, rating: int):
        """
        Rate the current item and schedule next review.
        
        Args:
            rating: Rating on 1-4 scale (1=Again, 2=Hard, 3=Good, 4=Easy)
        """
        if not self.current_item:
            return
        
        # Process the response
        result = self.fsrs.process_item_response(self.current_item.id, rating)
        
        # Update stats
        self.items_reviewed += 1
        self._update_progress()
        
        # Emit signal
        self.itemReviewed.emit(self.current_item.id, rating)
        
        # Log review in console
        logger.info(f"Item {self.current_item.id} reviewed with rating {rating}, next review in {result.get('interval', 0)} days")
        
        # Show next item
        self._next_item()
    
    def _show_completed(self):
        """Show the completion screen."""
        # Update stats
        self.stats_label.setText(f"Items reviewed: {self.items_reviewed}")
        
        # Switch to completed view
        self.content_stack.setCurrentWidget(self.completed_widget)
        
        # Update controls
        self.show_answer_button.setVisible(False)
        self.rating_frame.setVisible(False)
        self.done_button.setVisible(True) 