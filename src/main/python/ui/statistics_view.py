# ui/statistics_view.py

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple, Optional
import math

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QScrollArea, QSplitter, QTabWidget,
    QComboBox, QGroupBox, QFrame, QGridLayout, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QDateTime
from PyQt6.QtGui import QColor, QPen, QBrush, QPainter, QPainterPath
from PyQt6.QtCharts import QChart, QChartView, QLineSeries, QBarSeries, QBarSet, QBarCategoryAxis, QValueAxis

from sqlalchemy import func, and_, extract, case
from core.knowledge_base.models import (
    Document, Extract, LearningItem, ReviewLog, Category
)
from core.spaced_repetition import FSRSAlgorithm
from core.utils.category_helper import get_all_categories, populate_category_combo

logger = logging.getLogger(__name__)

class StatisticsWidget(QWidget):
    """Widget for displaying learning statistics."""
    
    def __init__(self, db_session, compact=False):
        super().__init__()
        
        self.db_session = db_session
        self.spaced_repetition = FSRSAlgorithm(db_session)
        self.compact = compact
        
        # Set up UI
        self._create_ui()
        
        # Load initial data
        self._load_data()
    
    def _create_ui(self):
        """Create the UI layout."""
        main_layout = QVBoxLayout(self)
        
        # Controls
        controls_layout = QHBoxLayout()
        
        # Time range selector
        range_label = QLabel("Time Range:")
        controls_layout.addWidget(range_label)
        
        self.range_combo = QComboBox()
        self.range_combo.addItems(["Last 7 Days", "Last 30 Days", "Last 90 Days", "Last Year", "All Time"])
        self.range_combo.setCurrentIndex(1)  # Default to Last 30 Days
        self.range_combo.currentTextChanged.connect(self._on_range_changed)
        controls_layout.addWidget(self.range_combo)
        
        # Category selector
        category_label = QLabel("Category:")
        controls_layout.addWidget(category_label)
        
        self.category_combo = QComboBox()
        self.category_combo.addItem("All Categories", None)
        self._populate_categories()
        self.category_combo.currentIndexChanged.connect(self._on_category_changed)
        controls_layout.addWidget(self.category_combo)
        
        # Refresh button
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self._on_refresh)
        controls_layout.addWidget(refresh_button)
        
        # Add controls to layout
        if not self.compact:
            main_layout.addLayout(controls_layout)
            
            # Create tab widget for different stats
            self.tabs = QTabWidget()
            self.tabs.setDocumentMode(True)
            
            # Create tabs
            self.overview_tab = self._create_overview_tab()
            self.retention_tab = self._create_retention_tab()
            self.workload_tab = self._create_workload_tab()
            
            # Add tabs
            self.tabs.addTab(self.overview_tab, "Overview")
            self.tabs.addTab(self.retention_tab, "Retention")
            self.tabs.addTab(self.workload_tab, "Workload")
            
            # Add tab widget to layout
            main_layout.addWidget(self.tabs)
        else:
            # Compact mode - show only essential stats
            self.summary_layout = QGridLayout()
            main_layout.addLayout(self.summary_layout)
            
            # Add a small version of the overview stats
            compact_overview = QHBoxLayout()
            
            # Document count
            self.doc_count_label = QLabel("Documents: 0")
            compact_overview.addWidget(self.doc_count_label)
            
            # Extract count
            self.extract_count_label = QLabel("Extracts: 0")
            compact_overview.addWidget(self.extract_count_label)
            
            # Learning items count
            self.item_count_label = QLabel("Items: 0")
            compact_overview.addWidget(self.item_count_label)
            
            # Due items
            self.due_count_label = QLabel("Due: 0")
            compact_overview.addWidget(self.due_count_label)
            
            main_layout.addLayout(compact_overview)
            
        # Set margins based on mode
        if self.compact:
            main_layout.setContentsMargins(5, 5, 5, 5)
            main_layout.setSpacing(5)
    
    def _create_overview_tab(self):
        """Create the overview tab with summary statistics."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Summary stats section
        summary_group = QGroupBox("Summary Statistics")
        summary_layout = QGridLayout(summary_group)
        
        # Document count
        doc_label = QLabel("Total Documents:")
        summary_layout.addWidget(doc_label, 0, 0)
        self.doc_count_label = QLabel("0")
        summary_layout.addWidget(self.doc_count_label, 0, 1)
        
        # Extract count
        extract_label = QLabel("Total Extracts:")
        summary_layout.addWidget(extract_label, 1, 0)
        self.extract_count_label = QLabel("0")
        summary_layout.addWidget(self.extract_count_label, 1, 1)
        
        # Learning item count
        item_label = QLabel("Total Learning Items:")
        summary_layout.addWidget(item_label, 2, 0)
        self.item_count_label = QLabel("0")
        summary_layout.addWidget(self.item_count_label, 2, 1)
        
        # Due items
        due_label = QLabel("Due Items:")
        summary_layout.addWidget(due_label, 0, 2)
        self.due_count_label = QLabel("0")
        summary_layout.addWidget(self.due_count_label, 0, 3)
        
        # Review stats
        review_label = QLabel("Reviews Completed:")
        summary_layout.addWidget(review_label, 1, 2)
        self.review_count_label = QLabel("0")
        summary_layout.addWidget(self.review_count_label, 1, 3)
        
        # Average rating
        rating_label = QLabel("Average Rating:")
        summary_layout.addWidget(rating_label, 2, 2)
        self.avg_rating_label = QLabel("0.0")
        summary_layout.addWidget(self.avg_rating_label, 2, 3)
        
        layout.addWidget(summary_group)
        
        # Activity chart
        activity_group = QGroupBox("Activity Over Time")
        activity_layout = QVBoxLayout(activity_group)
        self.activity_chart_view = QChartView()
        self.activity_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        activity_layout.addWidget(self.activity_chart_view)
        layout.addWidget(activity_group)
        
        # Progress chart
        progress_group = QGroupBox("Learning Progress")
        progress_layout = QVBoxLayout(progress_group)
        self.progress_chart_view = QChartView()
        self.progress_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        progress_layout.addWidget(self.progress_chart_view)
        layout.addWidget(progress_group)
        
        return tab
    
    def _create_retention_tab(self):
        """Create the retention tab with retention charts."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Retention chart
        retention_group = QGroupBox("Retention Rate")
        retention_layout = QVBoxLayout(retention_group)
        self.retention_chart_view = QChartView()
        self.retention_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        retention_layout.addWidget(self.retention_chart_view)
        layout.addWidget(retention_group)
        
        # Difficulty distribution chart
        difficulty_group = QGroupBox("Item Difficulty Distribution")
        difficulty_layout = QVBoxLayout(difficulty_group)
        self.difficulty_chart_view = QChartView()
        self.difficulty_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        difficulty_layout.addWidget(self.difficulty_chart_view)
        layout.addWidget(difficulty_group)
        
        return tab
    
    def _create_workload_tab(self):
        """Create the workload tab with workload forecasting."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Workload chart
        workload_group = QGroupBox("Review Workload Forecast")
        workload_layout = QVBoxLayout(workload_group)
        self.workload_chart_view = QChartView()
        self.workload_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        workload_layout.addWidget(self.workload_chart_view)
        layout.addWidget(workload_group)
        
        # Distribution chart
        distribution_group = QGroupBox("Item Status Distribution")
        distribution_layout = QVBoxLayout(distribution_group)
        self.distribution_chart_view = QChartView()
        self.distribution_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        distribution_layout.addWidget(self.distribution_chart_view)
        layout.addWidget(distribution_group)
        
        return tab
    
    def _populate_categories(self):
        """Populate the category combo box."""
        try:
            populate_category_combo(self.category_combo, self.db_session)
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to populate categories: {e}")
            
            # Fallback: Get categories directly from database
            # Clear current items (except "All Categories")
            while self.category_combo.count() > 1:
                self.category_combo.removeItem(1)
                
            categories = self.db_session.query(Category).order_by(Category.name).all()
            for category in categories:
                self.category_combo.addItem(category.name, category.id)
    
    def _load_data(self):
        """Load all data for the statistics view."""
        try:
            # Get selected time range and category
            time_range = self._get_time_range()
            category_id = self.category_combo.currentData()
            
            # Load summary statistics
            self._load_summary_stats(time_range, category_id)
            
            # Load charts only if not in compact mode
            if not self.compact:
                # Load activity chart
                self._load_activity_chart(time_range, category_id)
                
                # Load progress chart
                self._load_progress_chart(time_range, category_id)
                
                # Load retention chart
                self._load_retention_chart(time_range, category_id)
                
                # Load difficulty chart
                self._load_difficulty_chart(time_range, category_id)
                
                # Load workload chart
                self._load_workload_chart(category_id)
                
                # Load distribution chart
                self._load_distribution_chart(category_id)
        except Exception as e:
            logger.error(f"Error loading statistics data: {e}")
            # Show error message
            QMessageBox.warning(
                self, 
                "Data Loading Error",
                f"An error occurred while loading statistics:\n{str(e)}"
            )
    
    def _get_time_range(self) -> Tuple[datetime, datetime]:
        """Get date range based on selected option."""
        range_text = self.range_combo.currentText()
        end_date = datetime.utcnow()
        
        if range_text == "Last 7 Days":
            start_date = end_date - timedelta(days=7)
        elif range_text == "Last 30 Days":
            start_date = end_date - timedelta(days=30)
        elif range_text == "Last 90 Days":
            start_date = end_date - timedelta(days=90)
        elif range_text == "Last Year":
            start_date = end_date - timedelta(days=365)
        else:  # All Time
            start_date = datetime(2000, 1, 1)  # A date far in the past
        
        return start_date, end_date
    
    def _load_summary_stats(self, time_range: Tuple[datetime, datetime], category_id: Optional[int]):
        """Load summary statistics for the given time range and category."""
        try:
            start_date, end_date = time_range
            
            # Base query conditions
            conditions = [
                Document.created_at.between(start_date, end_date)
            ]
            
            # Add category filter if specified
            if category_id is not None:
                conditions.append(Document.category_id == category_id)
            
            # Documents count
            doc_count = self.db_session.query(func.count(Document.id)) \
                .filter(*conditions).scalar() or 0
            
            # Extracts count
            extract_conditions = [
                Extract.created_at.between(start_date, end_date)
            ]
            if category_id is not None:
                # Join to Document to filter by category
                extract_count = self.db_session.query(func.count(Extract.id)) \
                    .join(Document, Extract.document_id == Document.id) \
                    .filter(Document.category_id == category_id) \
                    .filter(Extract.created_at.between(start_date, end_date)) \
                    .scalar() or 0
            else:
                extract_count = self.db_session.query(func.count(Extract.id)) \
                    .filter(*extract_conditions).scalar() or 0
            
            # Learning items count
            item_conditions = [
                LearningItem.created_at.between(start_date, end_date)
            ]
            if category_id is not None:
                # For learning items, we need to join through extracts to get to documents
                item_count = self.db_session.query(func.count(LearningItem.id)) \
                    .join(Extract, LearningItem.extract_id == Extract.id) \
                    .join(Document, Extract.document_id == Document.id) \
                    .filter(Document.category_id == category_id) \
                    .filter(LearningItem.created_at.between(start_date, end_date)) \
                    .scalar() or 0
            else:
                item_count = self.db_session.query(func.count(LearningItem.id)) \
                    .filter(*item_conditions).scalar() or 0
            
            # Reviews count
            review_conditions = [
                ReviewLog.review_date.between(start_date, end_date)
            ]
            if category_id is not None:
                # Reviews need to be joined through items, extracts, and documents
                review_count = self.db_session.query(func.count(ReviewLog.id)) \
                    .join(LearningItem, ReviewLog.item_id == LearningItem.id) \
                    .join(Extract, LearningItem.extract_id == Extract.id) \
                    .join(Document, Extract.document_id == Document.id) \
                    .filter(Document.category_id == category_id) \
                    .filter(ReviewLog.review_date.between(start_date, end_date)) \
                    .scalar() or 0
            else:
                review_count = self.db_session.query(func.count(ReviewLog.id)) \
                    .filter(*review_conditions).scalar() or 0
            
            # Due items count (items due for review)
            due_count = self.spaced_repetition.get_due_items_count(category_id)
            
            # Average retention rate (can be calculated from review grades)
            retention = 0.0
            if review_count > 0:
                # Calculate retention as percentage of "good" reviews (grade >= 3)
                good_reviews = self.db_session.query(func.count(ReviewLog.id)) \
                    .filter(ReviewLog.grade >= 3) \
                    .filter(*review_conditions).scalar() or 0
                retention = (good_reviews / review_count) * 100.0
            
            # Update labels based on mode
            if self.compact:
                # Update compact view labels
                self.doc_count_label.setText(f"Documents: {doc_count}")
                self.extract_count_label.setText(f"Extracts: {extract_count}")
                self.item_count_label.setText(f"Items: {item_count}")
                self.due_count_label.setText(f"Due: {due_count}")
            else:
                # Update standard view labels
                self.doc_count_label.setText(f"{doc_count}")
                self.extract_count_label.setText(f"{extract_count}")
                self.item_count_label.setText(f"{item_count}")
                self.review_count_label.setText(f"{review_count}")
                self.due_count_label.setText(f"{due_count}")
                self.avg_rating_label.setText(f"{retention:.1f}%")
                
        except Exception as e:
            logger.error(f"Error loading summary statistics: {e}")
            # Handle error, perhaps show message to user
    
    def _load_activity_chart(self, time_range: Tuple[datetime, datetime], category_id: Optional[int]):
        """Load activity chart data."""
        start_date, end_date = time_range
        
        # Clear previous chart
        self.activity_chart.removeAllSeries()
        
        # Create series for extracts created and reviews performed
        extracts_series = QLineSeries()
        extracts_series.setName("Extracts Created")
        
        reviews_series = QLineSeries()
        reviews_series.setName("Reviews Performed")
        
        # Generate date list for x-axis
        days = (end_date - start_date).days + 1
        date_list = [start_date + timedelta(days=i) for i in range(days)]
        
        # Get extracts by date
        extract_query = self.db_session.query(
            func.date(Extract.created_date).label('date'),
            func.count(Extract.id).label('count')
        ).filter(
            Extract.created_date.between(start_date, end_date)
        ).group_by(
            func.date(Extract.created_date)
        )
        
        if category_id is not None:
            extract_query = extract_query.join(
                Document, Extract.document_id == Document.id
            ).filter(Document.category_id == category_id)
        
        extract_data = {row.date: row.count for row in extract_query.all()}
        
        # Get reviews by date
        review_query = self.db_session.query(
            func.date(ReviewLog.review_date).label('date'),
            func.count(ReviewLog.id).label('count')
        ).filter(
            ReviewLog.review_date.between(start_date, end_date)
        ).group_by(
            func.date(ReviewLog.review_date)
        )
        
        if category_id is not None:
            review_query = review_query.join(
                LearningItem, ReviewLog.learning_item_id == LearningItem.id
            ).join(
                Extract, LearningItem.extract_id == Extract.id
            ).join(
                Document, Extract.document_id == Document.id
            ).filter(Document.category_id == category_id)
        
        review_data = {row.date: row.count for row in review_query.all()}
        
        # Populate series
        for date in date_list:
            date_str = date.strftime('%Y-%m-%d')
            date_ts = QDateTime(date.year, date.month, date.day, 0, 0).toMSecsSinceEpoch()
            
            extract_count = extract_data.get(date_str, 0)
            extracts_series.append(date_ts, extract_count)
            
            review_count = review_data.get(date_str, 0)
            reviews_series.append(date_ts, review_count)
        
        # Add series to chart
        self.activity_chart.addSeries(extracts_series)
        self.activity_chart.addSeries(reviews_series)
        
        # Create axes
        self.activity_chart.createDefaultAxes()
        self.activity_chart.axes()[0].setTitleText("Date")
        self.activity_chart.axes()[1].setTitleText("Count")
    
    def _load_progress_chart(self, time_range: Tuple[datetime, datetime], category_id: Optional[int]):
        """Load progress chart data."""
        start_date, end_date = time_range
        
        # Clear previous chart
        self.progress_chart.removeAllSeries()
        
        # Create series for cumulative items created and reviewed
        items_series = QLineSeries()
        items_series.setName("Cumulative Items")
        
        reviewed_series = QLineSeries()
        reviewed_series.setName("Items Reviewed")
        
        # Generate date list for x-axis
        days = (end_date - start_date).days + 1
        date_list = [start_date + timedelta(days=i) for i in range(days)]
        
        # Get items created by date
        item_query = self.db_session.query(
            func.date(LearningItem.created_date).label('date'),
            func.count(LearningItem.id).label('count')
        ).filter(
            LearningItem.created_date.between(start_date, end_date)
        ).group_by(
            func.date(LearningItem.created_date)
        )
        
        if category_id is not None:
            item_query = item_query.join(
                Extract, LearningItem.extract_id == Extract.id
            ).join(
                Document, Extract.document_id == Document.id
            ).filter(Document.category_id == category_id)
        
        item_data = {row.date: row.count for row in item_query.all()}
        
        # Get items reviewed by date (first review only)
        reviewed_query = self.db_session.query(
            func.date(LearningItem.last_reviewed).label('date'),
            func.count(LearningItem.id).label('count')
        ).filter(
            LearningItem.last_reviewed.between(start_date, end_date)
        ).group_by(
            func.date(LearningItem.last_reviewed)
        )
        
        if category_id is not None:
            reviewed_query = reviewed_query.join(
                Extract, LearningItem.extract_id == Extract.id
            ).join(
                Document, Extract.document_id == Document.id
            ).filter(Document.category_id == category_id)
        
        reviewed_data = {row.date: row.count for row in reviewed_query.all()}
        
        # Populate series with cumulative data
        total_items = 0
        total_reviewed = 0
        
        for date in date_list:
            date_str = date.strftime('%Y-%m-%d')
            date_ts = QDateTime(date.year, date.month, date.day, 0, 0).toMSecsSinceEpoch()
            
            total_items += item_data.get(date_str, 0)
            items_series.append(date_ts, total_items)
            
            total_reviewed += reviewed_data.get(date_str, 0)
            reviewed_series.append(date_ts, total_reviewed)
        
        # Add series to chart
        self.progress_chart.addSeries(items_series)
        self.progress_chart.addSeries(reviewed_series)
        
        # Create axes
        self.progress_chart.createDefaultAxes()
        self.progress_chart.axes()[0].setTitleText("Date")
        self.progress_chart.axes()[1].setTitleText("Cumulative Count")
    
    def _load_retention_chart(self, time_range: Tuple[datetime, datetime], category_id: Optional[int]):
        """Load retention chart data."""
        start_date, end_date = time_range
        
        # Clear previous chart
        self.retention_chart.removeAllSeries()
        
        # Create series for retention rate
        retention_series = QLineSeries()
        retention_series.setName("Retention Rate")
        
        # Generate date list for x-axis
        days = (end_date - start_date).days + 1
        date_list = [start_date + timedelta(days=i) for i in range(days)]
        
        # Get retention rate by date
        # Retention is defined as the percentage of items with grade >= 3
        for date in date_list:
            query = self.db_session.query(
                func.sum(case((ReviewLog.grade >= 3, 1), else_=0)) * 100.0 / func.count(ReviewLog.id)
            ).filter(
                func.date(ReviewLog.review_date) == date.strftime('%Y-%m-%d')
            )
            
            if category_id is not None:
                query = query.join(
                    LearningItem, ReviewLog.learning_item_id == LearningItem.id
                ).join(
                    Extract, LearningItem.extract_id == Extract.id
                ).join(
                    Document, Extract.document_id == Document.id
                ).filter(Document.category_id == category_id)
            
            retention = query.scalar()
            
            if retention is not None:
                date_ts = QDateTime(date.year, date.month, date.day, 0, 0).toMSecsSinceEpoch()
                retention_series.append(date_ts, retention)
        
        # Add series to chart
        self.retention_chart.addSeries(retention_series)
        
        # Create axes
        self.retention_chart.createDefaultAxes()
        self.retention_chart.axes()[0].setTitleText("Date")
        self.retention_chart.axes()[1].setTitleText("Retention Rate (%)")
        self.retention_chart.axes()[1].setRange(0, 100)
    
    def _load_difficulty_chart(self, time_range: Tuple[datetime, datetime], category_id: Optional[int]):
        """Load difficulty distribution chart data."""
        start_date, end_date = time_range
        
        # Clear previous chart
        self.difficulty_chart.removeAllSeries()
        
        # Create bar series for difficulty distribution
        difficulty_set = QBarSet("Items")
        
        # Define difficulty bins
        bins = [
            {"min": 0.0, "max": 0.2, "label": "Very Easy"},
            {"min": 0.2, "max": 0.4, "label": "Easy"},
            {"min": 0.4, "max": 0.6, "label": "Medium"},
            {"min": 0.6, "max": 0.8, "label": "Hard"},
            {"min": 0.8, "max": 1.0, "label": "Very Hard"}
        ]
        
        # Get items by difficulty
        for bin in bins:
            query = self.db_session.query(func.count(LearningItem.id)).filter(
                LearningItem.difficulty.between(bin["min"], bin["max"]),
                LearningItem.created_date.between(start_date, end_date)
            )
            
            if category_id is not None:
                query = query.join(
                    Extract, LearningItem.extract_id == Extract.id
                ).join(
                    Document, Extract.document_id == Document.id
                ).filter(Document.category_id == category_id)
            
            count = query.scalar() or 0
            difficulty_set.append(count)
        
        # Create bar series
        series = QBarSeries()
        series.append(difficulty_set)
        
        # Add series to chart
        self.difficulty_chart.addSeries(series)
        
        # Create axes
        self.difficulty_chart.createDefaultAxes()
        
        # Set categories for X axis
        self.difficulty_chart.axes()[0].setCategories([bin["label"] for bin in bins])
        self.difficulty_chart.axes()[0].setTitleText("Difficulty")
        self.difficulty_chart.axes()[1].setTitleText("Count")
    
    def _load_workload_chart(self, category_id: Optional[int]):
        """Load workload forecast chart."""
        try:
            # Clear existing chart
            self.workload_chart.removeAllSeries()
            
            # Get workload forecast for the next 30 days
            workload = {}
            today = datetime.utcnow().date()
            
            # Use SQL query directly instead of the SM18 estimate_workload method
            for i in range(30):
                date = today + timedelta(days=i)
                date_start = datetime.combine(date, datetime.min.time())
                date_end = datetime.combine(date, datetime.max.time())
                date_str = date.strftime("%Y-%m-%d")
                
                # Count items due on this date
                query = self.db_session.query(func.count(LearningItem.id)).filter(
                    LearningItem.next_review.between(date_start, date_end)
                )
                
                # Apply category filter if specified
                if category_id is not None:
                    query = query.join(LearningItem.extract).join(Extract.document).filter(
                        Document.category_id == category_id
                    )
                
                count = query.scalar() or 0
                workload[date_str] = count
            
            # Create bar set for the chart
            bar_set = QBarSet("Items Due")
            
            # Add data points
            dates = []
            for i in range(30):
                date = today + timedelta(days=i)
                date_str = date.strftime("%Y-%m-%d")
                count = workload.get(date_str, 0)
                bar_set.append(count)
                dates.append(date_str)
            
            # Create bar series
            series = QBarSeries()
            series.append(bar_set)
            
            # Add series to chart
            self.workload_chart.addSeries(series)
            
            # Set axis
            axis_x = QBarCategoryAxis()
            axis_x.append(dates)
            self.workload_chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
            series.attachAxis(axis_x)
            
            axis_y = QValueAxis()
            max_count = max(workload.values()) if workload.values() else 10
            axis_y.setRange(0, max_count + 5)
            axis_y.setTitleText("Number of Items")
            self.workload_chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
            series.attachAxis(axis_y)
            
        except Exception as e:
            logger.exception(f"Error loading workload chart: {e}")
    
    def _load_distribution_chart(self, category_id: Optional[int]):
        """Load interval distribution chart data."""
        # Clear previous chart
        self.distribution_chart.removeAllSeries()
        
        # Create bar series for interval distribution
        interval_set = QBarSet("Items")
        
        # Define interval bins (in days)
        bins = [
            {"min": 0, "max": 1, "label": "New"},
            {"min": 1, "max": 7, "label": "1-7 days"},
            {"min": 7, "max": 30, "label": "1-4 weeks"},
            {"min": 30, "max": 90, "label": "1-3 months"},
            {"min": 90, "max": 365, "label": "3-12 months"},
            {"min": 365, "max": 999999, "label": ">1 year"}
        ]
        
        # Get items by interval
        for bin in bins:
            query = self.db_session.query(func.count(LearningItem.id)).filter(
                LearningItem.interval.between(bin["min"], bin["max"])
            )
            
            if category_id is not None:
                query = query.join(
                    Extract, LearningItem.extract_id == Extract.id
                ).join(
                    Document, Extract.document_id == Document.id
                ).filter(Document.category_id == category_id)
            
            count = query.scalar() or 0
            interval_set.append(count)
        
        # Create bar series
        series = QBarSeries()
        series.append(interval_set)
        
        # Add series to chart
        self.distribution_chart.addSeries(series)
        
        # Create axes
        self.distribution_chart.createDefaultAxes()
        
        # Set categories for X axis
        self.distribution_chart.axes()[0].setCategories([bin["label"] for bin in bins])
        self.distribution_chart.axes()[0].setTitleText("Interval")
        self.distribution_chart.axes()[1].setTitleText("Count")
    
    def refresh(self):
        """Refresh all statistics data."""
        self._load_data()
    
    @pyqtSlot()
    def _on_refresh(self):
        """Handler for refresh button click."""
        self.refresh()
    
    @pyqtSlot(str)
    def _on_range_changed(self, range_text):
        """Handler for time range selection change."""
        self._load_data()
    
    @pyqtSlot(int)
    def _on_category_changed(self, index):
        """Handler for category selection change."""
        self._load_data()
