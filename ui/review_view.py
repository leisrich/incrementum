# ui/review_view.py

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTextEdit, QProgressBar, QFrame,
    QRadioButton, QButtonGroup, QGroupBox, QTabWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QTimer

from core.knowledge_base.models import LearningItem, Extract
from core.spaced_repetition import FSRSAlgorithm
from core.utils.settings_manager import SettingsManager

logger = logging.getLogger(__name__)

class ReviewView(QWidget):
    """UI component for spaced repetition review sessions."""
    
    def __init__(self, items: List[LearningItem], spaced_repetition: FSRSAlgorithm, db_session):
        super().__init__()
        
        self.items = items
        self.current_index = 0
        self.spaced_repetition = spaced_repetition
        self.db_session = db_session
        
        # Stats
        self.stats = {
            'total': len(items),
            'completed': 0,
            'correct': 0,
            'incorrect': 0,
            'start_time': datetime.now(),
            'response_times': []
        }
        
        # Timer for response time
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.response_start_time = None
        
        # Set up UI
        self._create_ui()
        
        # Start review if we have items
        if self.items:
            self._show_next_item()
        else:
            self._show_no_items()
    
    def _create_ui(self):
        """Create the UI layout."""
        main_layout = QVBoxLayout(self)
        
        # Header area
        header_layout = QHBoxLayout()
        self.progress_label = QLabel("Progress: 0/0")
        header_layout.addWidget(self.progress_label)
        header_layout.addStretch()
        self.stats_label = QLabel("Correct: 0 | Incorrect: 0")
        header_layout.addWidget(self.stats_label)
        main_layout.addLayout(header_layout)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(max(1, len(self.items)))
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)
        
        # Question area
        self.question_box = QGroupBox("Question")
        question_layout = QVBoxLayout(self.question_box)
        self.question_edit = QTextEdit()
        self.question_edit.setReadOnly(True)
        question_layout.addWidget(self.question_edit)
        main_layout.addWidget(self.question_box)
        
        # Answer area (initially hidden)
        self.answer_box = QGroupBox("Answer")
        answer_layout = QVBoxLayout(self.answer_box)
        self.answer_edit = QTextEdit()
        self.answer_edit.setReadOnly(True)
        answer_layout.addWidget(self.answer_edit)
        self.answer_box.setVisible(False)
        main_layout.addWidget(self.answer_box)
        
        # Response buttons area
        self.response_box = QGroupBox("Your Response")
        response_layout = QVBoxLayout(self.response_box)
        
        # Show answer button
        self.show_answer_button = QPushButton("Show Answer")
        self.show_answer_button.clicked.connect(self._on_show_answer)
        response_layout.addWidget(self.show_answer_button)
        
        # Grade buttons (initially hidden)
        self.grade_widget = QWidget()
        grade_layout = QHBoxLayout(self.grade_widget)
        grade_layout.setContentsMargins(0, 0, 0, 0)
        
        # Grade radio buttons
        self.grade_group = QButtonGroup(self)
        
        grade_labels = [
            "0 - Complete blackout",
            "1 - Incorrect, familiar",
            "2 - Incorrect, easy recall",
            "3 - Correct, difficult",
            "4 - Correct, hesitation",
            "5 - Perfect recall"
        ]
        
        for i, label in enumerate(grade_labels):
            radio = QRadioButton(label)
            self.grade_group.addButton(radio, i)
            grade_layout.addWidget(radio)
        
        response_layout.addWidget(self.grade_widget)
        
        # Grade submission button
        self.submit_grade_button = QPushButton("Submit Grade")
        self.submit_grade_button.clicked.connect(self._on_submit_grade)
        response_layout.addWidget(self.submit_grade_button)
        
        # Initially hide grade controls
        self.grade_widget.setVisible(False)
        self.submit_grade_button.setVisible(False)
        
        main_layout.addWidget(self.response_box)
        
        # Add a separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        main_layout.addWidget(separator)
        
        # Session controls
        controls_layout = QHBoxLayout()
        controls_layout.addStretch()
        
        self.end_session_button = QPushButton("End Session")
        self.end_session_button.clicked.connect(self._on_end_session)
        controls_layout.addWidget(self.end_session_button)
        
        main_layout.addLayout(controls_layout)
    
    def _show_next_item(self):
        """Show the next item for review."""
        if self.current_index >= len(self.items):
            self._show_session_complete()
            return
        
        # Get current item
        item = self.items[self.current_index]
        
        # Update UI
        self.progress_label.setText(f"Progress: {self.current_index+1}/{len(self.items)}")
        self.progress_bar.setValue(self.current_index)
        
        # Display question
        self.question_edit.setText(item.question)
        
        # Hide answer
        self.answer_box.setVisible(False)
        self.answer_edit.setText(item.answer)
        
        # Show/hide appropriate controls
        self.show_answer_button.setVisible(True)
        self.grade_widget.setVisible(False)
        self.submit_grade_button.setVisible(False)
        
        # Start response timer
        self.response_start_time = datetime.now()
    
    def _show_no_items(self):
        """Show message when no items are available."""
        self.question_edit.setText("No items due for review")
        self.response_box.setVisible(False)
    
    def _show_session_complete(self):
        """Show session completion message and stats."""
        # Calculate stats
        total_time = datetime.now() - self.stats['start_time']
        avg_time = sum(self.stats['response_times']) / max(1, len(self.stats['response_times']))
        
        # Show completion message
        self.question_box.setTitle("Session Complete")
        self.question_edit.setText(
            f"Review session completed!\n\n"
            f"Total items: {self.stats['total']}\n"
            f"Correct: {self.stats['correct']}\n"
            f"Incorrect: {self.stats['incorrect']}\n"
            f"Accuracy: {self.stats['correct'] / max(1, self.stats['total']) * 100:.1f}%\n"
            f"Total time: {total_time}\n"
            f"Average response time: {avg_time:.1f} seconds"
        )
        
        # Hide answer and response areas
        self.answer_box.setVisible(False)
        self.response_box.setVisible(False)
    
    @pyqtSlot()
    def _on_show_answer(self):
        """Show the answer for the current item."""
        # Show answer
        self.answer_box.setVisible(True)
        
        # Hide show answer button, show grade controls
        self.show_answer_button.setVisible(False)
        self.grade_widget.setVisible(True)
        self.submit_grade_button.setVisible(True)
    
    @pyqtSlot()
    def _on_submit_grade(self):
        """Submit grade for the current item."""
        if self.current_index >= len(self.items):
            return
        
        # Get selected grade
        grade = self.grade_group.checkedId()
        if grade == -1:  # No button selected
            return
        
        # Calculate response time
        response_time = None
        if self.response_start_time:
            response_time = int((datetime.now() - self.response_start_time).total_seconds() * 1000)
            self.stats['response_times'].append((datetime.now() - self.response_start_time).total_seconds())
        
        # Get current item
        item = self.items[self.current_index]
        
        # Convert SM2 grade (0-5) to FSRS rating (1-4)
        fsrs_rating = 1  # Default to "Again"
        if grade <= 1:  # Complete blackout or familiar but forgotten
            fsrs_rating = 1  # Again
        elif grade == 2:  # Incorrect but easy to recall
            fsrs_rating = 2  # Hard
        elif grade in [3, 4]:  # Correct with effort or hesitation
            fsrs_rating = 3  # Good
        else:  # Perfect response (5)
            fsrs_rating = 4  # Easy
        
        # Process response with FSRS algorithm
        result = self.spaced_repetition.process_item_response(item.id, fsrs_rating, response_time)
        
        # Update stats
        self.stats['completed'] += 1
        if grade >= 3:  # Correct response
            self.stats['correct'] += 1
        else:  # Incorrect response
            self.stats['incorrect'] += 1
        
        self.stats_label.setText(f"Correct: {self.stats['correct']} | Incorrect: {self.stats['incorrect']}")
        
        # Move to next item
        self.current_index += 1
        self._show_next_item()
    
    @pyqtSlot()
    def _on_end_session(self):
        """End the review session."""
        # Show session summary
        self._show_session_complete()
        
        # Log session progress
        self._log_session_progress()
        
        # Find parent tab widget to navigate back
        parent = self.parent()
        while parent and not isinstance(parent, QTabWidget):
            parent = parent.parent()
            
        if parent:
            # Get current tab index
            current_index = parent.currentIndex()
            
            # If there's a tab to the left, go there
            if current_index > 0:
                parent.setCurrentIndex(current_index - 1)
            elif parent.count() > 1:
                # If there's no tab to the left but other tabs exist, go to the first tab
                parent.setCurrentIndex(0)
                
            # Close this tab (delayed to prevent issues)
            QTimer.singleShot(100, lambda: parent.removeTab(parent.indexOf(self)))
    
    def _log_session_progress(self):
        """Log the user's progress for the completed session."""
        try:
            from datetime import datetime
            
            # Create a progress log entry
            total_time = datetime.now() - self.stats['start_time']
            avg_response_time = sum(self.stats['response_times']) / max(1, len(self.stats['response_times']))
            
            # Log to console
            logger.info(f"Review session completed: {self.stats['completed']} items, "
                       f"{self.stats['correct']} correct ({self.stats['correct'] / max(1, self.stats['total']) * 100:.1f}%), "
                       f"avg response time: {avg_response_time:.1f}s")
            
            # Could also save to a database table if needed
            # This would require creating a new model for tracking progress over time
            
            # Update "last_review_date" for user preferences
            try:
                settings = SettingsManager()
                settings.set_setting("user", "last_review_date", datetime.now().isoformat())
                settings.set_setting("stats", "total_items_reviewed", 
                                   settings.get_setting("stats", "total_items_reviewed", 0) + self.stats['completed'])
                settings.set_setting("stats", "total_correct_answers", 
                                   settings.get_setting("stats", "total_correct_answers", 0) + self.stats['correct'])
                settings.save_settings()
            except Exception as e:
                logger.error(f"Failed to update review statistics: {e}")
                
        except Exception as e:
            logger.error(f"Error logging session progress: {e}")
