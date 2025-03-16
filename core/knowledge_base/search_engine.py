# core/knowledge_base/search_engine.py

import logging
import re
from typing import Dict, Any, List, Tuple, Optional, Set, Union
from datetime import datetime, timedelta

from sqlalchemy import func, and_, or_, not_, case, cast, Float
from sqlalchemy.orm import Session, aliased
from core.knowledge_base.models import Document, Category, Extract, LearningItem, Tag, ReviewLog
from PyQt5.QtCore import Qt, pyqtSlot, QTimer, QModelIndex, QPoint

logger = logging.getLogger(__name__)

class SearchEngine:
    """
    Advanced search engine for the knowledge base, supporting
    complex queries across different entity types.
    """
    
    def __init__(self, db_session: Session):
        self.db_session = db_session
    
    def search(self, query: str, entity_types: List[str] = None, filters: Dict[str, Any] = None, 
               sort_by: str = None, sort_order: str = "desc", limit: int = 100) -> Dict[str, List[Dict[str, Any]]]:
        """
        Perform a search across the knowledge base.
        
        Args:
            query: Search query string
            entity_types: List of entity types to search ('document', 'extract', 'learning_item')
            filters: Additional filters to apply
            sort_by: Field to sort by
            sort_order: Sort order ('asc' or 'desc')
            limit: Maximum number of results per entity type
            
        Returns:
            Dictionary mapping entity types to lists of results
        """
        if not entity_types:
            entity_types = ['document', 'extract', 'learning_item']
        
        results = {}
        
        # Parse query for advanced search syntax
        parsed_query = self._parse_query(query)
        
        # Search each entity type
        for entity_type in entity_types:
            if entity_type == 'document':
                results['documents'] = self._search_documents(parsed_query, filters, sort_by, sort_order, limit)
            elif entity_type == 'extract':
                results['extracts'] = self._search_extracts(parsed_query, filters, sort_by, sort_order, limit)
            elif entity_type == 'learning_item':
                results['learning_items'] = self._search_learning_items(parsed_query, filters, sort_by, sort_order, limit)
        
        return results
    
    def _parse_query(self, query: str) -> Dict[str, Any]:
        """
        Parse a search query string to extract search terms and operators.
        
        Supports:
        - Quoted phrases: "exact phrase"
        - Field search: field:term
        - Boolean operators: AND, OR, NOT
        - Parentheses for grouping
        
        Args:
            query: Search query string
            
        Returns:
            Dictionary with parsed query information
        """
        result = {
            'terms': [],
            'phrases': [],
            'field_terms': {},
            'exclude_terms': [],
            'raw_query': query
        }
        
        # If query is empty, return empty result
        if not query or query.strip() == '':
            return result
        
        # Extract quoted phrases
        phrases = re.findall(r'"([^"]*)"', query)
        result['phrases'] = phrases
        
        # Remove quoted phrases from query for further processing
        for phrase in phrases:
            query = query.replace(f'"{phrase}"', '')
        
        # Extract field searches (field:term)
        field_terms = re.findall(r'(\w+):(\S+)', query)
        for field, term in field_terms:
            if field not in result['field_terms']:
                result['field_terms'][field] = []
            result['field_terms'][field].append(term)
            
            # Remove field search from query
            query = query.replace(f'{field}:{term}', '')
        
        # Extract NOT terms
        not_terms = re.findall(r'NOT\s+(\S+)', query, re.IGNORECASE)
        result['exclude_terms'] = not_terms
        
        # Remove NOT terms from query
        for term in not_terms:
            query = re.sub(f'NOT\\s+{re.escape(term)}', '', query, flags=re.IGNORECASE)
        
        # Split remaining query into terms
        remaining_terms = [term for term in query.split() if term.upper() not in ['AND', 'OR', 'NOT']]
        result['terms'] = remaining_terms
        
        return result
    
    def _search_documents(self, parsed_query: Dict[str, Any], filters: Dict[str, Any] = None,
                          sort_by: str = None, sort_order: str = "desc", limit: int = 100) -> List[Dict[str, Any]]:
        """
        Search documents based on parsed query and filters.
        
        Args:
            parsed_query: Parsed query from _parse_query
            filters: Additional filters to apply
            sort_by: Field to sort by
            sort_order: Sort order ('asc' or 'desc')
            limit: Maximum number of results
            
        Returns:
            List of document results
        """
        # Start with base query
        query = self.db_session.query(Document)
        
        # Apply search terms
        query = self._apply_document_search_terms(query, parsed_query)
        
        # Apply filters
        if filters:
            query = self._apply_document_filters(query, filters)
        
        # Apply sorting
        if sort_by:
            query = self._apply_document_sorting(query, sort_by, sort_order)
        else:
            # Default sort by last_accessed
            query = query.order_by(Document.last_accessed.desc())
        
        # Execute query with limit
        documents = query.limit(limit).all()
        
        # Convert to dictionaries
        results = []
        for doc in documents:
            results.append({
                'id': doc.id,
                'title': doc.title,
                'author': doc.author,
                'content_type': doc.content_type,
                'imported_date': doc.imported_date,
                'last_accessed': doc.last_accessed,
                'category_id': doc.category_id,
                'extract_count': len(doc.extracts),
                'tags': [tag.name for tag in doc.tags]
            })
        
        return results
    
    def _apply_document_search_terms(self, query, parsed_query: Dict[str, Any]):
        """Apply search terms to document query."""
        if parsed_query['terms'] or parsed_query['phrases'] or parsed_query['field_terms'] or parsed_query['exclude_terms']:
            # Build filter conditions
            conditions = []
            
            # Add simple terms
            for term in parsed_query['terms']:
                term_filter = or_(
                    Document.title.ilike(f'%{term}%'),
                    Document.author.ilike(f'%{term}%')
                )
                conditions.append(term_filter)
            
            # Add phrases
            for phrase in parsed_query['phrases']:
                phrase_filter = or_(
                    Document.title.ilike(f'%{phrase}%'),
                    Document.author.ilike(f'%{phrase}%')
                )
                conditions.append(phrase_filter)
            
            # Add field terms
            for field, terms in parsed_query['field_terms'].items():
                for term in terms:
                    if field == 'title':
                        conditions.append(Document.title.ilike(f'%{term}%'))
                    elif field == 'author':
                        conditions.append(Document.author.ilike(f'%{term}%'))
                    elif field == 'type':
                        conditions.append(Document.content_type.ilike(f'%{term}%'))
                    elif field == 'tag':
                        conditions.append(Document.tags.any(Tag.name.ilike(f'%{term}%')))
            
            # Add exclude terms
            for term in parsed_query['exclude_terms']:
                exclude_filter = not_(or_(
                    Document.title.ilike(f'%{term}%'),
                    Document.author.ilike(f'%{term}%')
                ))
                conditions.append(exclude_filter)
            
            # Combine all conditions with AND
            if conditions:
                query = query.filter(and_(*conditions))
        
        return query
    
    def _apply_document_filters(self, query, filters: Dict[str, Any]):
        """Apply additional filters to document query."""
        if 'category_id' in filters and filters['category_id']:
            query = query.filter(Document.category_id == filters['category_id'])
        
        if 'content_type' in filters and filters['content_type']:
            query = query.filter(Document.content_type == filters['content_type'])
        
        if 'imported_after' in filters and filters['imported_after']:
            query = query.filter(Document.imported_date >= filters['imported_after'])
        
        if 'imported_before' in filters and filters['imported_before']:
            query = query.filter(Document.imported_date <= filters['imported_before'])
        
        if 'tags' in filters and filters['tags']:
            for tag in filters['tags']:
                query = query.filter(Document.tags.any(Tag.name == tag))
        
        if 'accessed_after' in filters and filters['accessed_after']:
            query = query.filter(Document.last_accessed >= filters['accessed_after'])
        
        return query
    
    def _apply_document_sorting(self, query, sort_by: str, sort_order: str):
        """Apply sorting to document query."""
        if sort_by == 'title':
            if sort_order == 'asc':
                query = query.order_by(Document.title.asc())
            else:
                query = query.order_by(Document.title.desc())
        elif sort_by == 'author':
            if sort_order == 'asc':
                query = query.order_by(Document.author.asc())
            else:
                query = query.order_by(Document.author.desc())
        elif sort_by == 'imported_date':
            if sort_order == 'asc':
                query = query.order_by(Document.imported_date.asc())
            else:
                query = query.order_by(Document.imported_date.desc())
        elif sort_by == 'last_accessed':
            if sort_order == 'asc':
                query = query.order_by(Document.last_accessed.asc())
            else:
                query = query.order_by(Document.last_accessed.desc())
        
        return query
    
    def _search_extracts(self, parsed_query: Dict[str, Any], filters: Dict[str, Any] = None,
                         sort_by: str = None, sort_order: str = "desc", limit: int = 100) -> List[Dict[str, Any]]:
        """
        Search extracts based on parsed query and filters.
        
        Args:
            parsed_query: Parsed query from _parse_query
            filters: Additional filters to apply
            sort_by: Field to sort by
            sort_order: Sort order ('asc' or 'desc')
            limit: Maximum number of results
            
        Returns:
            List of extract results
        """
        # Start with base query
        query = self.db_session.query(Extract).join(Document)
        
        # Apply search terms
        query = self._apply_extract_search_terms(query, parsed_query)
        
        # Apply filters
        if filters:
            query = self._apply_extract_filters(query, filters)
        
        # Apply sorting
        if sort_by:
            query = self._apply_extract_sorting(query, sort_by, sort_order)
        else:
            # Default sort by created_date
            query = query.order_by(Extract.created_date.desc())
        
        # Execute query with limit
        extracts = query.limit(limit).all()
        
        # Convert to dictionaries
        results = []
        for extract in extracts:
            # Truncate content if too long
            content = extract.content
            if len(content) > 200:
                content = content[:197] + "..."
            
            results.append({
                'id': extract.id,
                'content': content,
                'document_id': extract.document_id,
                'document_title': extract.document.title if extract.document else None,
                'priority': extract.priority,
                'created_date': extract.created_date,
                'last_reviewed': extract.last_reviewed,
                'processed': extract.processed,
                'tags': [tag.name for tag in extract.tags]
            })
        
        return results
    
    def _apply_extract_search_terms(self, query, parsed_query: Dict[str, Any]):
        """Apply search terms to extract query."""
        if parsed_query['terms'] or parsed_query['phrases'] or parsed_query['field_terms'] or parsed_query['exclude_terms']:
            # Build filter conditions
            conditions = []
            
            # Add simple terms
            for term in parsed_query['terms']:
                term_filter = or_(
                    Extract.content.ilike(f'%{term}%'),
                    Document.title.ilike(f'%{term}%')
                )
                conditions.append(term_filter)
            
            # Add phrases
            for phrase in parsed_query['phrases']:
                phrase_filter = or_(
                    Extract.content.ilike(f'%{phrase}%'),
                    Document.title.ilike(f'%{phrase}%')
                )
                conditions.append(phrase_filter)
            
            # Add field terms
            for field, terms in parsed_query['field_terms'].items():
                for term in terms:
                    if field == 'content':
                        conditions.append(Extract.content.ilike(f'%{term}%'))
                    elif field == 'document':
                        conditions.append(Document.title.ilike(f'%{term}%'))
                    elif field == 'priority':
                        try:
                            priority = int(term)
                            conditions.append(Extract.priority == priority)
                        except ValueError:
                            pass
                    elif field == 'tag':
                        conditions.append(Extract.tags.any(Tag.name.ilike(f'%{term}%')))
            
            # Add exclude terms
            for term in parsed_query['exclude_terms']:
                exclude_filter = not_(Extract.content.ilike(f'%{term}%'))
                conditions.append(exclude_filter)
            
            # Combine all conditions with AND
            if conditions:
                query = query.filter(and_(*conditions))
        
        return query
    
    def _apply_extract_filters(self, query, filters: Dict[str, Any]):
        """Apply additional filters to extract query."""
        if 'document_id' in filters and filters['document_id']:
            query = query.filter(Extract.document_id == filters['document_id'])
        
        if 'priority_min' in filters and filters['priority_min'] is not None:
            query = query.filter(Extract.priority >= filters['priority_min'])
        
        if 'priority_max' in filters and filters['priority_max'] is not None:
            query = query.filter(Extract.priority <= filters['priority_max'])
        
        if 'created_after' in filters and filters['created_after']:
            query = query.filter(Extract.created_date >= filters['created_after'])
        
        if 'created_before' in filters and filters['created_before']:
            query = query.filter(Extract.created_date <= filters['created_before'])
        
        if 'processed' in filters:
            query = query.filter(Extract.processed == filters['processed'])
        
        if 'tags' in filters and filters['tags']:
            for tag in filters['tags']:
                query = query.filter(Extract.tags.any(Tag.name == tag))
        
        return query
    
    def _apply_extract_sorting(self, query, sort_by: str, sort_order: str):
        """Apply sorting to extract query."""
        if sort_by == 'content':
            if sort_order == 'asc':
                query = query.order_by(Extract.content.asc())
            else:
                query = query.order_by(Extract.content.desc())
        elif sort_by == 'priority':
            if sort_order == 'asc':
                query = query.order_by(Extract.priority.asc())
            else:
                query = query.order_by(Extract.priority.desc())
        elif sort_by == 'created_date':
            if sort_order == 'asc':
                query = query.order_by(Extract.created_date.asc())
            else:
                query = query.order_by(Extract.created_date.desc())
        elif sort_by == 'document_title':
            if sort_order == 'asc':
                query = query.order_by(Document.title.asc())
            else:
                query = query.order_by(Document.title.desc())
        
        return query
    
    def _search_learning_items(self, parsed_query: Dict[str, Any], filters: Dict[str, Any] = None,
                               sort_by: str = None, sort_order: str = "desc", limit: int = 100) -> List[Dict[str, Any]]:
        """
        Search learning items based on parsed query and filters.
        
        Args:
            parsed_query: Parsed query from _parse_query
            filters: Additional filters to apply
            sort_by: Field to sort by
            sort_order: Sort order ('asc' or 'desc')
            limit: Maximum number of results
            
        Returns:
            List of learning item results
        """
        # Start with base query
        query = self.db_session.query(LearningItem).join(Extract).join(Document)
        
        # Apply search terms
        query = self._apply_learning_item_search_terms(query, parsed_query)
        
        # Apply filters
        if filters:
            query = self._apply_learning_item_filters(query, filters)
        
        # Apply sorting
        if sort_by:
            query = self._apply_learning_item_sorting(query, sort_by, sort_order)
        else:
            # Default sort by next_review
            query = query.order_by(LearningItem.next_review)
        
        # Execute query with limit
        items = query.limit(limit).all()
        
        # Convert to dictionaries
        results = []
        for item in items:
            # Truncate question/answer if too long
            question = item.question
            if len(question) > 200:
                question = question[:197] + "..."
            
            answer = item.answer
            if len(answer) > 200:
                answer = answer[:197] + "..."
            
            results.append({
                'id': item.id,
                'item_type': item.item_type,
                'question': question,
                'answer': answer,
                'extract_id': item.extract_id,
                'document_id': item.extract.document_id if item.extract else None,
                'document_title': item.extract.document.title if item.extract and item.extract.document else None,
                'priority': item.priority,
                'created_date': item.created_date,
                'last_reviewed': item.last_reviewed,
                'next_review': item.next_review,
                'interval': item.interval,
                'repetitions': item.repetitions,
                'easiness': item.easiness,
                'difficulty': item.difficulty
            })
        
        return results
    
    def _apply_learning_item_search_terms(self, query, parsed_query: Dict[str, Any]):
        """Apply search terms to learning item query."""
        if parsed_query['terms'] or parsed_query['phrases'] or parsed_query['field_terms'] or parsed_query['exclude_terms']:
            # Build filter conditions
            conditions = []
            
            # Add simple terms
            for term in parsed_query['terms']:
                term_filter = or_(
                    LearningItem.question.ilike(f'%{term}%'),
                    LearningItem.answer.ilike(f'%{term}%'),
                    Extract.content.ilike(f'%{term}%'),
                    Document.title.ilike(f'%{term}%')
                )
                conditions.append(term_filter)
            
            # Add phrases
            for phrase in parsed_query['phrases']:
                phrase_filter = or_(
                    LearningItem.question.ilike(f'%{phrase}%'),
                    LearningItem.answer.ilike(f'%{phrase}%'),
                    Extract.content.ilike(f'%{phrase}%'),
                    Document.title.ilike(f'%{phrase}%')
                )
                conditions.append(phrase_filter)
            
            # Add field terms
            for field, terms in parsed_query['field_terms'].items():
                for term in terms:
                    if field == 'question':
                        conditions.append(LearningItem.question.ilike(f'%{term}%'))
                    elif field == 'answer':
                        conditions.append(LearningItem.answer.ilike(f'%{term}%'))
                    elif field == 'type':
                        conditions.append(LearningItem.item_type.ilike(f'%{term}%'))
                    elif field == 'extract':
                        conditions.append(Extract.content.ilike(f'%{term}%'))
                    elif field == 'document':
                        conditions.append(Document.title.ilike(f'%{term}%'))
                    elif field == 'priority':
                        try:
                            priority = int(term)
                            conditions.append(LearningItem.priority == priority)
                        except ValueError:
                            pass
                    elif field == 'difficulty':
                        try:
                            difficulty = float(term)
                            conditions.append(LearningItem.difficulty == difficulty)
                        except ValueError:
                            pass
            
            # Add exclude terms
            for term in parsed_query['exclude_terms']:
                exclude_filter = not_(or_(
                    LearningItem.question.ilike(f'%{term}%'),
                    LearningItem.answer.ilike(f'%{term}%')
                ))
                conditions.append(exclude_filter)
            
            # Combine all conditions with AND
            if conditions:
                query = query.filter(and_(*conditions))
        
        return query
    
    def _apply_learning_item_filters(self, query, filters: Dict[str, Any]):
        """Apply additional filters to learning item query."""
        if 'extract_id' in filters and filters['extract_id']:
            query = query.filter(LearningItem.extract_id == filters['extract_id'])
        
        if 'document_id' in filters and filters['document_id']:
            query = query.filter(Extract.document_id == filters['document_id'])
        
        if 'item_type' in filters and filters['item_type']:
            query = query.filter(LearningItem.item_type == filters['item_type'])
        
        if 'priority_min' in filters and filters['priority_min'] is not None:
            query = query.filter(LearningItem.priority >= filters['priority_min'])
        
        if 'priority_max' in filters and filters['priority_max'] is not None:
            query = query.filter(LearningItem.priority <= filters['priority_max'])
        
        if 'created_after' in filters and filters['created_after']:
            query = query.filter(LearningItem.created_date >= filters['created_after'])
        
        if 'created_before' in filters and filters['created_before']:
            query = query.filter(LearningItem.created_date <= filters['created_before'])
        
        if 'due' in filters and filters['due']:
            query = query.filter(
                (LearningItem.next_review <= datetime.utcnow()) | 
                (LearningItem.next_review == None)
            )
        
        if 'interval_min' in filters and filters['interval_min'] is not None:
            query = query.filter(LearningItem.interval >= filters['interval_min'])
        
        if 'interval_max' in filters and filters['interval_max'] is not None:
            query = query.filter(LearningItem.interval <= filters['interval_max'])
        
        if 'difficulty_min' in filters and filters['difficulty_min'] is not None:
            query = query.filter(LearningItem.difficulty >= filters['difficulty_min'])
        
        if 'difficulty_max' in filters and filters['difficulty_max'] is not None:
            query = query.filter(LearningItem.difficulty <= filters['difficulty_max'])
        
        if 'last_reviewed_after' in filters and filters['last_reviewed_after']:
            query = query.filter(LearningItem.last_reviewed >= filters['last_reviewed_after'])
        
        return query
    
    def _apply_learning_item_sorting(self, query, sort_by: str, sort_order: str):
        """Apply sorting to learning item query."""
        if sort_by == 'question':
            if sort_order == 'asc':
                query = query.order_by(LearningItem.question.asc())
            else:
                query = query.order_by(LearningItem.question.desc())
        elif sort_by == 'priority':
            if sort_order == 'asc':
                query = query.order_by(LearningItem.priority.asc())
            else:
                query = query.order_by(LearningItem.priority.desc())
        elif sort_by == 'created_date':
            if sort_order == 'asc':
                query = query.order_by(LearningItem.created_date.asc())
            else:
                query = query.order_by(LearningItem.created_date.desc())
        elif sort_by == 'next_review':
            if sort_order == 'asc':
                query = query.order_by(LearningItem.next_review.asc())
            else:
                query = query.order_by(LearningItem.next_review.desc())
        elif sort_by == 'difficulty':
            if sort_order == 'asc':
                query = query.order_by(LearningItem.difficulty.asc())
            else:
                query = query.order_by(LearningItem.difficulty.desc())
        elif sort_by == 'interval':
            if sort_order == 'asc':
                query = query.order_by(LearningItem.interval.asc())
            else:
                query = query.order_by(LearningItem.interval.desc())
        
        return query


# ui/search_view.py

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QLineEdit, QComboBox, QTabWidget,
    QGroupBox, QCheckBox, QRadioButton, QButtonGroup,
    QFormLayout, QSpinBox, QDateEdit, QTableWidget,
    QTableWidgetItem, QHeaderView, QCompleter, QMenu,
    QSplitter, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QDate, QSize
from PyQt6.QtGui import QIcon, QAction

from core.knowledge_base.models import Document, Category, Extract, LearningItem, Tag
from core.knowledge_base.search_engine import SearchEngine

logger = logging.getLogger(__name__)

class SearchView(QWidget):
    """Widget for performing advanced searches."""
    
    itemSelected = pyqtSignal(str, int)  # type, id
    
    def __init__(self, db_session):
        super().__init__()
        
        self.db_session = db_session
        self.search_engine = SearchEngine(db_session)
        
        # Create UI
        self._create_ui()
    
    def _create_ui(self):
        """Create the UI layout."""
        main_layout = QVBoxLayout(self)
        
        # Search input area
        search_layout = QHBoxLayout()
        
        # Search box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Enter search query (e.g., \"neural networks\" tag:science)")
        self.search_box.returnPressed.connect(self._on_search)
        search_layout.addWidget(self.search_box)
        
        # Entity type selector
        self.entity_type_combo = QComboBox()
        self.entity_type_combo.addItem("All Types", ['document', 'extract', 'learning_item'])
        self.entity_type_combo.addItem("Documents", ['document'])
        self.entity_type_combo.addItem("Extracts", ['extract'])
        self.entity_type_combo.addItem("Learning Items", ['learning_item'])
        search_layout.addWidget(self.entity_type_combo)
        
        # Search button
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self._on_search)
        search_layout.addWidget(self.search_button)
        
        main_layout.addLayout(search_layout)
        
        # Create splitter for filters and results
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Filters area
        filters_widget = QWidget()
        filters_layout = QVBoxLayout(filters_widget)
        
        # Filter groups
        self._create_date_filters(filters_layout)
        self._create_priority_filters(filters_layout)
        self._create_category_filters(filters_layout)
        self._create_tag_filters(filters_layout)
        self._create_learning_filters(filters_layout)
        
        # Apply filters button
        self.apply_filters_button = QPushButton("Apply Filters")
        self.apply_filters_button.clicked.connect(self._on_search)
        filters_layout.addWidget(self.apply_filters_button)
        
        # Reset filters button
        self.reset_filters_button = QPushButton("Reset Filters")
        self.reset_filters_button.clicked.connect(self._on_reset_filters)
        filters_layout.addWidget(self.reset_filters_button)
        
        filters_layout.addStretch()
        
        # Results area
        results_widget = QWidget()
        results_layout = QVBoxLayout(results_widget)
        
        # Results tabs
        self.results_tabs = QTabWidget()
        
        # Documents tab
        self.documents_tab = QWidget()
        documents_layout = QVBoxLayout(self.documents_tab)
        
        self.documents_table = QTableWidget()
        self.documents_table.setColumnCount(5)
        self.documents_table.setHorizontalHeaderLabels(["Title", "Author", "Type", "Date", "Tags"])
        self.documents_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.documents_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.documents_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.documents_table.doubleClicked.connect(self._on_document_selected)
        self.documents_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.documents_table.customContextMenuRequested.connect(self._on_document_context_menu)
        
        documents_layout.addWidget(self.documents_table)
        
        self.results_tabs.addTab(self.documents_tab, "Documents (0)")
        
        # Extracts tab
        self.extracts_tab = QWidget()
        extracts_layout = QVBoxLayout(self.extracts_tab)
        
        self.extracts_table = QTableWidget()
        self.extracts_table.setColumnCount(4)
        self.extracts_table.setHorizontalHeaderLabels(["Content", "Document", "Priority", "Date"])
        self.extracts_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.extracts_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.extracts_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.extracts_table.doubleClicked.connect(self._on_extract_selected)
        self.extracts_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.extracts_table.customContextMenuRequested.connect(self._on_extract_context_menu)
        
        extracts_layout.addWidget(self.extracts_table)
        
        self.results_tabs.addTab(self.extracts_tab, "Extracts (0)")
        
        # Learning items tab
        self.learning_items_tab = QWidget()
        learning_items_layout = QVBoxLayout(self.learning_items_tab)
        
        self.learning_items_table = QTableWidget()
        self.learning_items_table.setColumnCount(5)
        self.learning_items_table.setHorizontalHeaderLabels(["Question", "Answer", "Type", "Next Review", "Difficulty"])
        self.learning_items_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.learning_items_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.learning_items_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.learning_items_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.learning_items_table.doubleClicked.connect(self._on_learning_item_selected)
        self.learning_items_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.learning_items_table.customContextMenuRequested.connect(self._on_learning_item_context_menu)
        
        learning_items_layout.addWidget(self.learning_items_table)
        
        self.results_tabs.addTab(self.learning_items_tab, "Learning Items (0)")
        
        results_layout.addWidget(self.results_tabs)
        
        # Add widgets to splitter
        splitter.addWidget(filters_widget)
        splitter.addWidget(results_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        
        main_layout.addWidget(splitter)
        
        # Status bar
        self.status_label = QLabel("Ready")
        main_layout.addWidget(self.status_label)
    
    def _create_date_filters(self, parent_layout):
        """Create date filter controls."""
        date_group = QGroupBox("Date Filters")
        date_layout = QFormLayout(date_group)
        
        # Created after
        self.created_after = QDateEdit()
        self.created_after.setCalendarPopup(True)
        self.created_after.setDate(QDate.currentDate().addMonths(-6))
        self.created_after.setDisplayFormat("yyyy-MM-dd")
        self.created_after_check = QCheckBox()
        self.created_after_check.setChecked(False)
        date_layout.addRow("Created after:", self.created_after)
        date_layout.addRow("Enable:", self.created_after_check)
        
        # Created before
        self.created_before = QDateEdit()
        self.created_before.setCalendarPopup(True)
        self.created_before.setDate(QDate.currentDate())
        self.created_before.setDisplayFormat("yyyy-MM-dd")
        self.created_before_check = QCheckBox()
        self.created_before_check.setChecked(False)
        date_layout.addRow("Created before:", self.created_before)
        date_layout.addRow("Enable:", self.created_before_check)
        
        parent_layout.addWidget(date_group)
    
    def _create_priority_filters(self, parent_layout):
        """Create priority filter controls."""
        priority_group = QGroupBox("Priority Filters")
        priority_layout = QFormLayout(priority_group)
        
        # Priority range
        self.priority_min = QSpinBox()
        self.priority_min.setRange(0, 100)
        self.priority_min.setValue(0)
        self.priority_min_check = QCheckBox()
        self.priority_min_check.setChecked(False)
        priority_layout.addRow("Minimum priority:", self.priority_min)
        priority_layout.addRow("Enable:", self.priority_min_check)
        
        self.priority_max = QSpinBox()
        self.priority_max.setRange(0, 100)
        self.priority_max.setValue(100)
        self.priority_max_check = QCheckBox()
        self.priority_max_check.setChecked(False)
        priority_layout.addRow("Maximum priority:", self.priority_max)
        priority_layout.addRow("Enable:", self.priority_max_check)
        
        parent_layout.addWidget(priority_group)
    
    def _create_category_filters(self, parent_layout):
        """Create category filter controls."""
        category_group = QGroupBox("Category Filter")
        category_layout = QVBoxLayout(category_group)
        
        # Category combo
        self.category_combo = QComboBox()
        self.category_combo.addItem("All Categories", None)
        
        # Populate categories
        categories = self.db_session.query(Category).all()
        for category in categories:
            self.category_combo.addItem(category.name, category.id)
        
        category_layout.addWidget(self.category_combo)
        
        parent_layout.addWidget(category_group)
    
    def _create_tag_filters(self, parent_layout):
        """Create tag filter controls."""
        tag_group = QGroupBox("Tag Filters")
        tag_layout = QVBoxLayout(tag_group)
        
        # Tag input
        self.tag_input = QLineEdit()
        self.tag_input.setPlaceholderText("Enter tags (comma-separated)")
        
        # Populate tag completer
        tags = self.db_session.query(Tag.name).all()
        tag_list = [tag[0] for tag in tags]
        completer = QCompleter(tag_list)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.tag_input.setCompleter(completer)
        
        tag_layout.addWidget(self.tag_input)
        
        parent_layout.addWidget(tag_group)
    
    def _create_learning_filters(self, parent_layout):
        """Create learning-specific filter controls."""
        learning_group = QGroupBox("Learning Filters")
        learning_layout = QFormLayout(learning_group)
        
        # Due items only
        self.due_only = QCheckBox()
        self.due_only.setChecked(False)
        learning_layout.addRow("Due items only:", self.due_only)
        
        # Item type
        self.item_type_combo = QComboBox()
        self.item_type_combo.addItem("All Types", None)
        self.item_type_combo.addItem("Question-Answer", "qa")
        self.item_type_combo.addItem("Cloze Deletion", "cloze")
        self.item_type_combo.addItem("Image", "image")
        learning_layout.addRow("Item type:", self.item_type_combo)
        
        # Difficulty range
        self.difficulty_min = QDoubleSpinBox()
        self.difficulty_min.setRange(0.0, 1.0)
        self.difficulty_min.setSingleStep(0.1)
        self.difficulty_min.setValue(0.0)
        self.difficulty_min_check = QCheckBox()
        self.difficulty_min_check.setChecked(False)
        learning_layout.addRow("Minimum difficulty:", self.difficulty_min)
        learning_layout.addRow("Enable:", self.difficulty_min_check)
        
        self.difficulty_max = QDoubleSpinBox()
        self.difficulty_max.setRange(0.0, 1.0)
        self.difficulty_max.setSingleStep(0.1)
        self.difficulty_max.setValue(1.0)
        self.difficulty_max_check = QCheckBox()
        self.difficulty_max_check.setChecked(False)
        learning_layout.addRow("Maximum difficulty:", self.difficulty_max)
        learning_layout.addRow("Enable:", self.difficulty_max_check)
        
        parent_layout.addWidget(learning_group)
    
    def _get_search_filters(self) -> Dict[str, Any]:
        """Get current filter values."""
        filters = {}
        
        # Date filters
        if self.created_after_check.isChecked():
            filters['created_after'] = self.created_after.date().toPyDate()
        
        if self.created_before_check.isChecked():
            filters['created_before'] = self.created_before.date().toPyDate()
        
        # Priority filters
        if self.priority_min_check.isChecked():
            filters['priority_min'] = self.priority_min.value()
        
        if self.priority_max_check.isChecked():
            filters['priority_max'] = self.priority_max.value()
        
        # Category filter
        category_id = self.category_combo.currentData()
        if category_id is not None:
            filters['category_id'] = category_id
        
        # Tag filters
        tag_text = self.tag_input.text().strip()
        if tag_text:
            filters['tags'] = [tag.strip() for tag in tag_text.split(',') if tag.strip()]
        
        # Learning filters
        if self.due_only.isChecked():
            filters['due'] = True
        
        item_type = self.item_type_combo.currentData()
        if item_type:
            filters['item_type'] = item_type
        
        if self.difficulty_min_check.isChecked():
            filters['difficulty_min'] = self.difficulty_min.value()
        
        if self.difficulty_max_check.isChecked():
            filters['difficulty_max'] = self.difficulty_max.value()
        
        return filters
    
    @pyqtSlot()
    def _on_search(self):
        """Handle search button click."""
        query = self.search_box.text().strip()
        entity_types = self.entity_type_combo.currentData()
        filters = self._get_search_filters()
        
        # Update status
        self.status_label.setText("Searching...")
        QApplication.processEvents()  # Update UI
        
        try:
            # Perform search
            results = self.search_engine.search(query, entity_types, filters)
            
            # Update results tables
            self._update_document_results(results.get('documents', []))
            self._update_extract_results(results.get('extracts', []))
            self._update_learning_item_results(results.get('learning_items', []))
            
            # Update status
            total_count = sum(len(results.get(t, [])) for t in ['documents', 'extracts', 'learning_items'])
            self.status_label.setText(f"Found {total_count} results")
            
        except Exception as e:
            logger.exception(f"Error performing search: {e}")
            self.status_label.setText(f"Error: {str(e)}")
    
    def _update_document_results(self, documents: List[Dict[str, Any]]):
        """Update documents table with search results."""
        # Clear table
        self.documents_table.setRowCount(0)
        
        # Add rows
        for i, doc in enumerate(documents):
            self.documents_table.insertRow(i)
            
            # Title
            title_item = QTableWidgetItem(doc['title'])
            title_item.setData(Qt.ItemDataRole.UserRole, doc['id'])
            self.documents_table.setItem(i, 0, title_item)
            
            # Author
            author_item = QTableWidgetItem(doc['author'] or "")
            self.documents_table.setItem(i, 1, author_item)
            
            # Type
            type_item = QTableWidgetItem(doc['content_type'])
            self.documents_table.setItem(i, 2, type_item)
            
            # Date
            date_str = doc['imported_date'].strftime("%Y-%m-%d") if doc['imported_date'] else ""
            date_item = QTableWidgetItem(date_str)
            self.documents_table.setItem(i, 3, date_item)
            
            # Tags
            tags_str = ", ".join(doc['tags']) if doc['tags'] else ""
            tags_item = QTableWidgetItem(tags_str)
            self.documents_table.setItem(i, 4, tags_item)
        
        # Update tab title
        self.results_tabs.setTabText(0, f"Documents ({len(documents)})")
    
    def _update_extract_results(self, extracts: List[Dict[str, Any]]):
        """Update extracts table with search results."""
        # Clear table
        self.extracts_table.setRowCount(0)
        
        # Add rows
        for i, extract in enumerate(extracts):
            self.extracts_table.insertRow(i)
            
            # Content
            content_item = QTableWidgetItem(extract['content'])
            content_item.setData(Qt.ItemDataRole.UserRole, extract['id'])
            self.extracts_table.setItem(i, 0, content_item)
            
            # Document
            document_item = QTableWidgetItem(extract['document_title'] or "")
            document_item.setData(Qt.ItemDataRole.UserRole, extract['document_id'])
            self.extracts_table.setItem(i, 1, document_item)
            
            # Priority
            priority_item = QTableWidgetItem(str(extract['priority']))
            self.extracts_table.setItem(i, 2, priority_item)
            
            # Date
            date_str = extract['created_date'].strftime("%Y-%m-%d") if extract['created_date'] else ""
            date_item = QTableWidgetItem(date_str)
            self.extracts_table.setItem(i, 3, date_item)
        
        # Update tab title
        self.results_tabs.setTabText(1, f"Extracts ({len(extracts)})")
    
    def _update_learning_item_results(self, items: List[Dict[str, Any]]):
        """Update learning items table with search results."""
        # Clear table
        self.learning_items_table.setRowCount(0)
        
        # Add rows
        for i, item in enumerate(items):
            self.learning_items_table.insertRow(i)
            
            # Question
            question_item = QTableWidgetItem(item['question'])
            question_item.setData(Qt.ItemDataRole.UserRole, item['id'])
            self.learning_items_table.setItem(i, 0, question_item)
            
            # Answer
            answer_item = QTableWidgetItem(item['answer'])
            self.learning_items_table.setItem(i, 1, answer_item)
            
            # Type
            type_item = QTableWidgetItem(item['item_type'])
            self.learning_items_table.setItem(i, 2, type_item)
            
            # Next review
            if item['next_review']:
                next_review_str = item['next_review'].strftime("%Y-%m-%d")
                
                # Highlight due items
                if item['next_review'] <= datetime.utcnow():
                    next_review_str += " (Due)"
            else:
                next_review_str = "New"
                
            next_review_item = QTableWidgetItem(next_review_str)
            self.learning_items_table.setItem(i, 3, next_review_item)
            
            # Difficulty
            difficulty_str = f"{item['difficulty']:.2f}" if item['difficulty'] is not None else ""
            difficulty_item = QTableWidgetItem(difficulty_str)
            self.learning_items_table.setItem(i, 4, difficulty_item)
        
        # Update tab title
        self.results_tabs.setTabText(2, f"Learning Items ({len(items)})")
    
    @pyqtSlot()
    def _on_reset_filters(self):
        """Handle reset filters button click."""
        # Reset date filters
        self.created_after_check.setChecked(False)
        self.created_before_check.setChecked(False)
        
        # Reset priority filters
        self.priority_min_check.setChecked(False)
        self.priority_max_check.setChecked(False)
        
        # Reset category filter
        self.category_combo.setCurrentIndex(0)
        
        # Reset tag filter
        self.tag_input.clear()
        
        # Reset learning filters
        self.due_only.setChecked(False)
        self.item_type_combo.setCurrentIndex(0)
        self.difficulty_min_check.setChecked(False)
        self.difficulty_max_check.setChecked(False)
    
    @pyqtSlot(QModelIndex)
    def _on_document_selected(self, index):
        """Handle document selection."""
        if not index.isValid():
            return
        
        document_id = self.documents_table.item(index.row(), 0).data(Qt.ItemDataRole.UserRole)
        self.itemSelected.emit("document", document_id)
    
    @pyqtSlot(QModelIndex)
    def _on_extract_selected(self, index):
        """Handle extract selection."""
        if not index.isValid():
            return
        
        extract_id = self.extracts_table.item(index.row(), 0).data(Qt.ItemDataRole.UserRole)
        self.itemSelected.emit("extract", extract_id)
    
    @pyqtSlot(QModelIndex)
    def _on_learning_item_selected(self, index):
        """Handle learning item selection."""
        if not index.isValid():
            return
        
        item_id = self.learning_items_table.item(index.row(), 0).data(Qt.ItemDataRole.UserRole)
        self.itemSelected.emit("learning_item", item_id)
    
    @pyqtSlot(QPoint)
    def _on_document_context_menu(self, pos):
        """Show context menu for document table."""
        index = self.documents_table.indexAt(pos)
        if not index.isValid():
            return
        
        document_id = self.documents_table.item(index.row(), 0).data(Qt.ItemDataRole.UserRole)
        
        menu = QMenu(self)
        open_action = menu.addAction("Open Document")
        open_action.triggered.connect(lambda: self.itemSelected.emit("document", document_id))
        
        menu.addSeparator()
        
        copy_action = menu.addAction("Copy Title")
        copy_action.triggered.connect(lambda: QApplication.clipboard().setText(self.documents_table.item(index.row(), 0).text()))
        
        menu.exec(self.documents_table.viewport().mapToGlobal(pos))
    
    @pyqtSlot(QPoint)
    def _on_extract_context_menu(self, pos):
        """Show context menu for extract table."""
        index = self.extracts_table.indexAt(pos)
        if not index.isValid():
            return
        
        extract_id = self.extracts_table.item(index.row(), 0).data(Qt.ItemDataRole.UserRole)
        document_id = self.extracts_table.item(index.row(), 1).data(Qt.ItemDataRole.UserRole)
        
        menu = QMenu(self)
        open_extract_action = menu.addAction("Open Extract")
        open_extract_action.triggered.connect(lambda: self.itemSelected.emit("extract", extract_id))
        
        if document_id:
            open_document_action = menu.addAction("Open Source Document")
            open_document_action.triggered.connect(lambda: self.itemSelected.emit("document", document_id))
        
        menu.addSeparator()
        
        copy_action = menu.addAction("Copy Content")
        copy_action.triggered.connect(lambda: QApplication.clipboard().setText(self.extracts_table.item(index.row(), 0).text()))
        
        menu.exec(self.extracts_table.viewport().mapToGlobal(pos))
    
    @pyqtSlot(QPoint)
    def _on_learning_item_context_menu(self, pos):
        """Show context menu for learning item table."""
        index = self.learning_items_table.indexAt(pos)
        if not index.isValid():
            return
        
        item_id = self.learning_items_table.item(index.row(), 0).data(Qt.ItemDataRole.UserRole)
        
        menu = QMenu(self)
        open_action = menu.addAction("View Learning Item")
        open_action.triggered.connect(lambda: self.itemSelected.emit("learning_item", item_id))
        
        menu.addSeparator()
        
        copy_question_action = menu.addAction("Copy Question")
        copy_question_action.triggered.connect(lambda: QApplication.clipboard().setText(self.learning_items_table.item(index.row(), 0).text()))
        
        copy_answer_action = menu.addAction("Copy Answer")
        copy_answer_action.triggered.connect(lambda: QApplication.clipboard().setText(self.learning_items_table.item(index.row(), 1).text()))
        
        menu.exec(self.learning_items_table.viewport().mapToGlobal(pos))
