"""Migration script to add YouTube playlist tables."""

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, Float, ForeignKey,
    create_engine, MetaData, Table
)
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()
metadata = MetaData()

def upgrade(engine):
    """Add YouTube playlist tables."""
    
    # Create categories table reference
    categories = Table(
        'categories', metadata,
        Column('id', Integer, primary_key=True),
        extend_existing=True
    )
    
    # Create tables
    youtube_playlists = Table(
        'youtube_playlists', metadata,
        Column('id', Integer, primary_key=True),
        Column('playlist_id', String(100), nullable=False, unique=True),
        Column('title', String(255), nullable=False),
        Column('channel_title', String(255)),
        Column('description', Text),
        Column('thumbnail_url', String(512)),
        Column('video_count', Integer, default=0),
        Column('category_id', Integer, ForeignKey('categories.id'), nullable=True),
        Column('imported_date', DateTime, default=datetime.utcnow),
        Column('last_updated', DateTime, default=datetime.utcnow)
    )

    youtube_playlist_videos = Table(
        'youtube_playlist_videos', metadata,
        Column('id', Integer, primary_key=True),
        Column('playlist_id', Integer, ForeignKey('youtube_playlists.id'), nullable=False),
        Column('video_id', String(20), nullable=False),
        Column('document_id', Integer, ForeignKey('documents.id'), nullable=True),
        Column('title', String(255)),
        Column('position', Integer),
        Column('duration', Integer, default=0),
        Column('watched_position', Integer, default=0),
        Column('watched_percent', Float, default=0.0),
        Column('last_watched', DateTime, nullable=True),
        Column('marked_complete', Boolean, default=False)
    )

    # Create tables
    metadata.create_all(engine)

def downgrade(engine):
    """Remove YouTube playlist tables."""
    metadata.bind = engine
    youtube_playlist_videos = Table('youtube_playlist_videos', metadata)
    youtube_playlists = Table('youtube_playlists', metadata)
    
    # Drop tables in correct order
    youtube_playlist_videos.drop(engine, checkfirst=True)
    youtube_playlists.drop(engine, checkfirst=True) 