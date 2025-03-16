# ui/statistics_view.py

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple, Optional
import math

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QScrollArea, QSplitter, QTabWidget,
    QComboBox, QGroupBox, QFrame, QGridLayout
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QDateTime
from PyQt6.QtGui import QColor, QPen, QBrush, QPainter, QPainterPath
from PyQt6.QtCharts import QChart, QChartView, QLineSeries, QBarSeries, QBarSet

from sqlalchemy import func, and_, extract
from core.knowledge_base.models import (
    Document, Extract, LearningItem, ReviewLog, Category
)
from core.spaced_repetition.sm18 import SM18Algorithm

logger = logging.getLogger(__name__)

class StatisticsWidget(QWidget):
    """Widget for displaying learning statistics."""
    
    def __init__(self, db_session):
        super().__init__()
        
        self.db_session = db_session
        self.spaced_repetition = SM18Algorithm(db_session)
        
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
        self.range_combo.addItems(["Last 7 Days", "Last 30 Days", "Last 90 Days", "All Time"])
        self.range_combo.setCurrentText("Last 30 Days")
        self.range_combo.currentTextChanged.connect(self._on_range_changed)
        controls_layout.addWidget(self.range_combo)
        
        # Category filter
        category_label = QLabel("Category:")
        controls_layout.addWidget(category_label)
        
        self.category_combo = QComboBox()
        self.category_combo.addItem("All Categories", None)
        self._populate_categories()
        self.category_combo.currentIndexChanged.connect(self._on_category_changed)
        controls_layout.addWidget(self.category_combo)
        
        controls_layout.addStretch()
        
        # Refresh button
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self._on_refresh)
        controls_layout.addWidget(self.refresh_button)
        
        main_layout.addLayout(controls_layout)
        
        # Tab widget for different statistics
        self.tab_widget = QTabWidget()
        
        # Overview tab
        self.overview_tab = QWidget()
        self._create_overview_tab()
        self.tab_widget.addTab(self.overview_tab, "Overview")
        
        # Retention tab
        self.retention_tab = QWidget()
        self._create_retention_tab()
        self.tab_widget.addTab(self.retention_tab, "Retention")
        
        # Workload tab
        self.workload_tab = QWidget()
        self._create_workload_tab()
        self.tab_widget.addTab(self.workload_tab, "Workload")
        
        # Add tab widget to main layout
        main_layout.addWidget(self.tab_widget)
    
    def _create_overview_tab(self):
        """Create the overview tab."""
        layout = QVBoxLayout(self.overview_tab)
        
        # Summary statistics
        summary_group = QGroupBox("Summary")
        summary_layout = QGridLayout(summary_group)
        
        # Create labels for statistics
        self.total_documents_label = QLabel("Total Documents: 0")
        summary_layout.addWidget(self.total_documents_label, 0, 0)
        
        self.total_extracts_label = QLabel("Total Extracts: 0")
        summary_layout.addWidget(self.total_extracts_label, 0, 1)
        
        self.total_items_label = QLabel("Total Learning Items: 0")
        summary_layout.addWidget(self.total_items_label, 1, 0)
        
        self.total_reviews_label = QLabel("Total Reviews: 0")
        summary_layout.addWidget(self.total_reviews_label, 1, 1)
        
        self.avg_retention_label = QLabel("Average Retention: 0%")
        summary_layout.addWidget(self.avg_retention_label, 2, 0)
        
        self.due_items_label = QLabel("Due Items: 0")
        summary_layout.addWidget(self.due_items_label, 2, 1)
        
        layout.addWidget(summary_group)
        
        # Charts
        charts_layout = QHBoxLayout()
        
        # Activity chart
        self.activity_chart = QChart()
        self.activity_chart.setTitle("Learning Activity")
        self.activity_chart.legend().setVisible(True)
        
        self.activity_chart_view = QChartView(self.activity_chart)
        self.activity_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        charts_layout.addWidget(self.activity_chart_view)
        
        # Progress chart
        self.progress_chart = QChart()
        self.progress_chart.setTitle("Learning Progress")
        self.progress_chart.legend().setVisible(True)
        
        self.progress_chart_view = QChartView(self.progress_chart)
        self.progress_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        charts_layout.addWidget(self.progress_chart_view)
        
        layout.addLayout(charts_layout)
    
    def _create_retention_tab(self):
        """Create the retention tab."""
        layout = QVBoxLayout(self.retention_tab)
        
        # Retention chart
        self.retention_chart = QChart()
        self.retention_chart.setTitle("Retention Over Time")
        self.retention_chart.legend().setVisible(True)
        
        self.retention_chart_view = QChartView(self.retention_chart)
        self.retention_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        layout.addWidget(self.retention_chart_view)
        
        # Difficulty distribution chart
        self.difficulty_chart = QChart()
        self.difficulty_chart.setTitle("Item Difficulty Distribution")
        self.difficulty_chart.legend().setVisible(True)
        
        self.difficulty_chart_view = QChartView(self.difficulty_chart)
        self.difficulty_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        layout.addWidget(self.difficulty_chart_view)
    
    def _create_workload_tab(self):
        """Create the workload tab."""
        layout = QVBoxLayout(self.workload_tab)
        
        # Workload forecast chart
        self.workload_chart = QChart()
        self.workload_chart.setTitle("Review Workload Forecast")
        self.workload_chart.legend().setVisible(True)
        
        self.workload_chart_view = QChartView(self.workload_chart)
        self.workload_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        layout.addWidget(self.workload_chart_view)
        
        # Item distribution chart
        self.distribution_chart = QChart()
        self.distribution_chart.setTitle("Learning Items by Interval")
        self.distribution_chart.legend().setVisible(True)
        
        self.distribution_chart_view = QChartView(self.distribution_chart)
        self.distribution_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        layout.addWidget(self.distribution_chart_view)
    
    def _populate_categories(self):
        """Populate the category selector."""
        categories = self.db_session.query(Category).all()
        
        for category in categories:
            self.category_combo.addItem(category.name, category.id)
    
    def _load_data(self):
        """Load statistics data."""
        # Get filter parameters
        time_range = self._get_time_range()
        category_id = self.category_combo.currentData()
        
        # Load summary statistics
        self._load_summary_stats(time_range, category_id)
        
        # Load chart data
        self._load_activity_chart(time_range, category_id)
        self._load_progress_chart(time_range, category_id)
        self._load_retention_chart(time_range, category_id)
        self._load_difficulty_chart(time_range, category_id)
        self._load_workload_chart(category_id)
        self._load_distribution_chart(category_id)
    
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
        else:  # All Time
            start_date = datetime(2000, 1, 1)  # A date far in the past
        
        return start_date, end_date
    
    def _load_summary_stats(self, time_range: Tuple[datetime, datetime], category_id: Optional[int]):
        """Load summary statistics."""
        start_date, end_date = time_range
        
        # Build base queries
        doc_query = self.db_session.query(func.count(Document.id))
        extract_query = self.db_session.query(func.count(Extract.id))
        item_query = self.db_session.query(func.count(LearningItem.id))
        review_query = self.db_session.query(func.count(ReviewLog.id))
        
        # Apply category filter if specified
        if category_id is not None:
            doc_query = doc_query.filter(Document.category_id == category_id)
            
            extract_query = extract_query.join(
                Document, Extract.document_id == Document.id
            ).filter(Document.category_id == category_id)
            
            item_query = item_query.join(
                Extract, LearningItem.extract_id == Extract.id
            ).join(
                Document, Extract.document_id == Document.id
            ).filter(Document.category_id == category_id)
            
            review_query = review_query.join(
                LearningItem, ReviewLog.learning_item_id == LearningItem.id
            ).join(
                Extract, LearningItem.extract_id == Extract.id
            ).join(
                Document, Extract.document_id == Document.id
            ).filter(Document.category_id == category_id)
        
        # Apply time filter to reviews
        review_query = review_query.filter(
            ReviewLog.review_date.between(start_date, end_date)
        )
        
        # Get counts
        doc_count = doc_query.scalar() or 0
        extract_count = extract_query.scalar() or 0
        item_count = item_query.scalar() or 0
        review_count = review_query.scalar() or 0
        
        # Calculate average retention
        # Retention is defined as the percentage of items with grade >= 3
        retention_query = self.db_session.query(
            func.sum(case((ReviewLog.grade >= 3, 1), else_=0)) * 100.0 / func.count(ReviewLog.id)
        ).filter(
            ReviewLog.review_date.between(start_date, end_date)
        )
        
        if category_id is not None:
            retention_query = retention_query.join(
                LearningItem, ReviewLog.learning_item_id == LearningItem.id
            ).join(
                Extract, LearningItem.extract_id == Extract.id
            ).join(
                Document, Extract.document_id == Document.id
            ).filter(Document.category_id == category_id)
        
        retention = retention_query.scalar() or 0
        
        # Get due items
        due_query = self.db_session.query(func.count(LearningItem.id)).filter(
            (LearningItem.next_review <= datetime.utcnow()) | 
            (LearningItem.next_review == None)
        )
        
        if category_id is not None:
            due_query = due_query.join(
                Extract, LearningItem.extract_id == Extract.id
            ).join(
                Document, Extract.document_id == Document.id
            ).filter(Document.category_id == category_id)
        
        due_count = due_query.scalar() or 0
        
        # Update labels
        self.total_documents_label.setText(f"Total Documents: {doc_count}")
        self.total_extracts_label.setText(f"Total Extracts: {extract_count}")
        self.total_items_label.setText(f"Total Learning Items: {item_count}")
        self.total_reviews_label.setText(f"Total Reviews: {review_count}")
        self.avg_retention_label.setText(f"Average Retention: {retention:.1f}%")
        self.due_items_label.setText(f"Due Items: {due_count}")
    
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
        """Load workload forecast chart data."""
        # Clear previous chart
        self.workload_chart.removeAllSeries()
        
        # Create series for workload forecast
        workload_series = QLineSeries()
        workload_series.setName("Due Items")
        
        # Get workload data
        workload = self.spaced_repetition.estimate_workload(30)  # 30 days
        
        # Convert to series data
        for date_str, count in workload.items():
            date = datetime.strptime(date_str, "%Y-%m-%d")
            date_ts = QDateTime(date.year, date.month, date.day, 0, 0).toMSecsSinceEpoch()
            workload_series.append(date_ts, count)
        
        # Add series to chart
        self.workload_chart.addSeries(workload_series)
        
        # Create axes
        self.workload_chart.createDefaultAxes()
        self.workload_chart.axes()[0].setTitleText("Date")
        self.workload_chart.axes()[1].setTitleText("Items Due")
    
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
    
    @pyqtSlot(str)
    def _on_range_changed(self, range_text):
        """Handle time range change."""
        self._load_data()
    
    @pyqtSlot(int)
    def _on_category_changed(self, index):
        """Handle category change."""
        self._load_data()
    
    @pyqtSlot()
    def _on_refresh(self):
        """Handle refresh button click."""
        self._load_data()
