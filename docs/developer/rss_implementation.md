# RSS Feed Implementation Guide

This document describes the architecture and implementation details of the RSS feed functionality in Incrementum. It's intended for developers who need to maintain or extend this feature.

## Architecture Overview

The RSS feed functionality consists of three main components:

1. **Data Models**: Database models for storing RSS feeds and entries
2. **RSS Feed Manager**: Core logic for managing and processing feeds
3. **UI Components**: User interface for interacting with RSS feeds

### File Structure

```
core/
  knowledge_base/
    models.py            # Contains RSSFeed and RSSFeedEntry models
  utils/
    rss_feed_manager.py  # Core RSS processing logic
ui/
  rss_view.py            # Main RSS UI component
  dialogs/
    rss_feed_dialog.py   # Dialog for adding/editing feeds
```

## Data Models

The RSS functionality uses two main database models defined in `core/knowledge_base/models.py`:

### RSSFeed

Represents a subscribed RSS feed.

| Field | Type | Description |
|-------|------|-------------|
| id | Integer | Primary key |
| title | String | Feed title |
| url | String | Feed URL |
| category_id | Integer | Foreign key to Category (optional) |
| last_checked | DateTime | When the feed was last checked |
| check_frequency | Integer | How often to check for updates (minutes) |
| auto_import | Boolean | Whether to automatically import new items |
| max_items_to_keep | Integer | Maximum number of items to keep (0 = keep all) |
| enabled | Boolean | Whether the feed is active |

### RSSFeedEntry

Represents an individual entry/article from an RSS feed.

| Field | Type | Description |
|-------|------|-------------|
| id | Integer | Primary key |
| feed_id | Integer | Foreign key to RSSFeed |
| entry_id | String | Unique identifier for the entry (from feed) |
| title | String | Entry title |
| publish_date | DateTime | When the entry was published |
| link_url | String | URL to the original article |
| processed | Boolean | Whether the entry has been processed |
| processed_date | DateTime | When the entry was processed |
| document_id | Integer | Foreign key to Document (if imported) |

### Relationships

```
RSSFeed (1) --< RSSFeedEntry (many)
RSSFeed (many) --< Document (many) (through association table)
```

## Core Functionality: RSSFeedManager

The `RSSFeedManager` class in `core/utils/rss_feed_manager.py` handles the core RSS functionality:

### Key Methods

#### Feed Management

- `get_all_feeds()`: Retrieves all RSS feeds from the database
- `add_feed(url, title, category_id)`: Adds a new feed
- `delete_feed(feed_id, delete_documents)`: Removes a feed and optionally its documents
- `get_feeds_due_for_update()`: Gets feeds that need to be checked for updates

#### Feed Processing

- `update_feed(feed)`: Updates a single feed with new entries
- `update_all_feeds()`: Updates all feeds
- `import_new_entries(feed)`: Imports unprocessed entries from a feed
- `import_all_new_entries()`: Imports entries from all feeds with auto-import enabled

#### Background Processing

- `start_feed_update_timer()`: Starts the background thread for updating feeds
- `stop_feed_update_timer()`: Stops the background thread
- `_update_feeds_thread()`: Thread method that periodically checks for updates

#### Content Processing

- `_download_article_content(url)`: Downloads and extracts article content
- `_save_content_to_file(content, title)`: Saves content as an HTML file
- `_cleanup_old_documents(feed)`: Removes oldest documents if exceeding max_items_to_keep

### Background Thread

The `RSSFeedManager` uses a background thread to periodically check for updates:

1. The thread is started when the application launches
2. It sleeps for a configurable interval between checks
3. During each cycle, it checks for feeds due for updates
4. It updates each due feed and processes new entries if auto-import is enabled
5. The thread runs as a daemon thread so it terminates when the application closes

## UI Components

### RSSView

The `RSSView` class in `ui/rss_view.py` is the main UI component for RSS functionality:

- Three-panel interface with feeds, entries, and content preview
- Methods for loading, refreshing, and importing feed content
- Context menus for feed and entry management
- Filter options for viewing entries (all, unread, imported)

#### Key Signals

- `open_document_signal`: Emitted when opening an imported document

### RSSFeedDialog

The `RSSFeedDialog` class in `ui/dialogs/rss_feed_dialog.py` provides the interface for managing feeds:

- Table of feeds with their properties
- Table of entries for the selected feed
- Buttons for adding, refreshing, and importing feeds
- Context menu for feed operations

#### AddEditFeedDialog

The `AddEditFeedDialog` class (inner class in `RSSFeedDialog`) provides the interface for adding or editing a feed:

- Form for feed properties
- Button for testing the feed URL
- Category selection for organizing imported content

## Integration with MainWindow

The RSS functionality is integrated into the main application through:

1. **Menu item**: Tools > Manage RSS Feeds
2. **Method**: `_on_manage_rss_feeds()` in MainWindow
3. **Background updates**: MainWindow calls `start_feed_update_timer()` during initialization

## Extending the RSS Functionality

### Adding New Feed Properties

1. Update the `RSSFeed` model in `models.py`
2. Modify the `AddEditFeedDialog` to include the new property
3. Update the `RSSFeedManager` to handle the new property

### Supporting New Feed Types

The system uses `feedparser` which supports various feed formats. To add support for custom formats:

1. Extend the `update_feed` method in `RSSFeedManager`
2. Add custom parsing logic for the new format
3. Ensure entry identification remains consistent

### Enhancing Content Processing

To improve content extraction:

1. Modify the `_download_article_content` method in `RSSFeedManager`
2. Consider using additional libraries like `newspaper3k` for better content extraction
3. Add custom parsing for specific websites if needed

## Common Issues and Solutions

### Memory Usage

If the application is consuming excessive memory:

1. Ensure `max_items_to_keep` is set to a reasonable value
2. Check that `_cleanup_old_documents` is being called correctly
3. Consider implementing additional cleanup for cached content

### Performance

If feed updates are slow:

1. Increase check intervals for less important feeds
2. Consider implementing parallel updates for multiple feeds
3. Add timeout handling for unresponsive feed sources

### Error Handling

The current implementation includes error handling for:

1. Network errors during feed retrieval
2. Parse errors for malformed feeds
3. Database errors during feed operations

## Testing

When modifying the RSS functionality, test:

1. Adding feeds with various formats (RSS 2.0, Atom, etc.)
2. Handling of feeds with different article structures
3. Background updates and auto-import behavior
4. Error conditions (network failures, invalid feeds) 