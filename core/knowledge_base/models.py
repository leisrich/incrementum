# core/knowledge_base/models.py

from datetime import datetime
from sqlalchemy import (
    Column, Integer, Float, String, Text, DateTime, 
    Boolean, ForeignKey, Table, create_engine
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

Base = declarative_base()

# Association tables for many-to-many relationships
document_tag_association = Table(
    'document_tag', Base.metadata,
    Column('document_id', Integer, ForeignKey('documents.id')),
    Column('tag_id', Integer, ForeignKey('tags.id'))
)

extract_tag_association = Table(
    'extract_tag', Base.metadata,
    Column('extract_id', Integer, ForeignKey('extracts.id')),
    Column('tag_id', Integer, ForeignKey('tags.id'))
)

# RSS Feed - Document association
rss_feed_document_association = Table(
    'rss_feed_document', Base.metadata,
    Column('rss_feed_id', Integer, ForeignKey('rss_feeds.id')),
    Column('document_id', Integer, ForeignKey('documents.id'))
)

class Category(Base):
    """Hierarchical category for organizing knowledge."""
    __tablename__ = 'categories'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    parent_id = Column(Integer, ForeignKey('categories.id'), nullable=True)
    
    # Relationships
    parent = relationship("Category", remote_side=[id], backref="children")
    documents = relationship("Document", back_populates="category")

class Tag(Base):
    """Tags for cross-referencing knowledge items."""
    __tablename__ = 'tags'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    
    # Relationships
    documents = relationship("Document", secondary=document_tag_association, back_populates="tags")
    extracts = relationship("Extract", secondary=extract_tag_association, back_populates="tags")

class Document(Base):
    """Document imported into the system."""
    __tablename__ = 'documents'

    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    author = Column(String(255))
    source_url = Column(String(512))
    file_path = Column(String(512), nullable=False)
    content_type = Column(String(50), nullable=False)  # pdf, html, txt, etc.
    imported_date = Column(DateTime, default=datetime.utcnow)
    last_accessed = Column(DateTime, default=datetime.utcnow)
    processing_progress = Column(Float, default=0.0)  # 0-100%
    category_id = Column(Integer, ForeignKey('categories.id'))
    position = Column(Integer, nullable=True)  # Reading position
    
    # Queue management fields
    priority = Column(Integer, default=50)  # 1-100 scale
    next_reading_date = Column(DateTime, nullable=True)  # When to read next
    last_reading_date = Column(DateTime, nullable=True)  # When last read
    reading_count = Column(Integer, default=0)  # Number of times read
    stability = Column(Float, nullable=True)  # Stability for FSRS algorithm
    difficulty = Column(Float, nullable=True)  # Difficulty for FSRS algorithm
    reps = Column(Integer, default=0)  # Successful repetition count for FSRS
    
    # Relationships
    category = relationship("Category", back_populates="documents")
    extracts = relationship("Extract", back_populates="document", cascade="all, delete-orphan")
    tags = relationship("Tag", secondary=document_tag_association, back_populates="documents")

class Extract(Base):
    """Knowledge extract from a document."""
    __tablename__ = 'extracts'

    id = Column(Integer, primary_key=True)
    content = Column(Text, nullable=False)
    context = Column(Text)  # Surrounding context for the extract
    document_id = Column(Integer, ForeignKey('documents.id'), nullable=False)
    parent_id = Column(Integer, ForeignKey('extracts.id'))  # For hierarchical extracts
    position = Column(String(255))  # Position info in source document
    priority = Column(Integer, default=50)  # 1-100 scale
    created_date = Column(DateTime, default=datetime.utcnow)
    last_reviewed = Column(DateTime, nullable=True)
    processed = Column(Boolean, default=False)  # Whether converted to learning items
    
    # Relationships
    document = relationship("Document", back_populates="extracts")
    parent = relationship("Extract", remote_side=[id], backref="children")
    learning_items = relationship("LearningItem", back_populates="extract", cascade="all, delete-orphan")
    tags = relationship("Tag", secondary=extract_tag_association, back_populates="extracts")

class LearningItem(Base):
    """Item for spaced repetition review."""
    __tablename__ = 'learning_items'

    id = Column(Integer, primary_key=True)
    extract_id = Column(Integer, ForeignKey('extracts.id'), nullable=False)
    item_type = Column(String(20), nullable=False)  # qa, cloze, image, etc.
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    created_date = Column(DateTime, default=datetime.utcnow)
    last_reviewed = Column(DateTime, nullable=True)
    
    # Spaced repetition algorithm fields
    interval = Column(Integer, default=0)  # Days until next review
    repetitions = Column(Integer, default=0)  # Legacy: Number of successful repetitions
    easiness = Column(Float, default=2.5)  # Legacy: E-factor in SM algorithm
    next_review = Column(DateTime, nullable=True)
    
    # FSRS algorithm fields
    stability = Column(Float, nullable=True)  # Memory stability
    difficulty = Column(Float, default=0.0)  # Item difficulty
    reps = Column(Integer, default=0)  # Successful repetition count for FSRS
    
    # Priority and metadata
    priority = Column(Integer, default=50)  # Inherited from extract initially
    
    # Relationships
    extract = relationship("Extract", back_populates="learning_items")
    review_history = relationship("ReviewLog", back_populates="learning_item", cascade="all, delete-orphan")

class ReviewLog(Base):
    """Log of review sessions for learning items."""
    __tablename__ = 'review_logs'

    id = Column(Integer, primary_key=True)
    learning_item_id = Column(Integer, ForeignKey('learning_items.id'), nullable=False)
    review_date = Column(DateTime, default=datetime.utcnow)
    grade = Column(Integer, nullable=False)  # 0-5 scale (SM algorithm)
    response_time = Column(Integer)  # Response time in milliseconds
    scheduled_interval = Column(Integer)  # Interval that was scheduled
    actual_interval = Column(Integer)  # Actual interval (may differ if overdue)
    
    # Relationships
    learning_item = relationship("LearningItem", back_populates="review_history")

class RSSFeed(Base):
    """RSS Feed source for auto-importing documents."""
    __tablename__ = 'rss_feeds'

    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    url = Column(String(1024), nullable=False, unique=True)
    category_id = Column(Integer, ForeignKey('categories.id'))
    last_checked = Column(DateTime, nullable=True)
    check_frequency = Column(Integer, default=60)  # In minutes
    auto_import = Column(Boolean, default=True)  # Auto import new items
    enabled = Column(Boolean, default=True)  # Feed enabled/disabled
    created_date = Column(DateTime, default=datetime.utcnow)
    max_items_to_keep = Column(Integer, default=50)  # Max number of items to keep
    
    # Relationships
    category = relationship("Category", backref="rss_feeds")
    documents = relationship("Document", secondary=rss_feed_document_association)
    
    def __repr__(self):
        return f"<RSSFeed '{self.title}' ({self.url})>"

class RSSFeedEntry(Base):
    """Keeps track of RSS feed entries that have been processed."""
    __tablename__ = 'rss_feed_entries'
    
    id = Column(Integer, primary_key=True)
    feed_id = Column(Integer, ForeignKey('rss_feeds.id'), nullable=False)
    entry_id = Column(String(1024), nullable=False)  # RSS entry ID or GUID
    document_id = Column(Integer, ForeignKey('documents.id'), nullable=True)
    title = Column(String(512))
    publish_date = Column(DateTime, nullable=True)
    processed_date = Column(DateTime, default=datetime.utcnow)
    processed = Column(Boolean, default=False)
    link_url = Column(String(1024), nullable=True)  # Actual URL to the content
    
    # Relationships
    feed = relationship("RSSFeed", backref="entries")
    document = relationship("Document", backref="rss_entry")
    
    def __repr__(self):
        return f"<RSSFeedEntry '{self.title}' ({self.entry_id})>"

# Database initialization
def init_database():
    """Initialize the database."""
    from appdirs import user_data_dir
    import os
    
    # Create application data directory if it doesn't exist
    data_dir = user_data_dir("Incrementum", "Incrementum")
    os.makedirs(data_dir, exist_ok=True)
    
    # Create database file
    db_path = os.path.join(data_dir, "incrementum.db")
    engine = create_engine(f"sqlite:///{db_path}")
    
    # Create tables
    Base.metadata.create_all(engine)
    
    # Create session factory
    Session = sessionmaker(bind=engine)
    return Session()
