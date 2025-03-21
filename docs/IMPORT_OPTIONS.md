# Import Options in Incrementum

Incrementum provides several ways to import content into your knowledge base, including files, URLs, YouTube videos, RSS feeds, and ArXiv papers. This guide covers these import options with a focus on YouTube, RSS Feeds, and ArXiv.

## Table of Contents

1. [YouTube Videos](#youtube-videos)
2. [RSS Feeds](#rss-feeds)
3. [ArXiv Papers](#arxiv-papers)
4. [Other Import Options](#other-import-options)

## YouTube Videos

The YouTube import feature allows you to import videos along with their transcripts directly into Incrementum, making it easy to learn from video content.

### Features

- Import videos with automatic transcript retrieval
- View transcripts alongside videos in a split view
- Create knowledge extracts directly from video transcripts
- Automatic bookmark creation for transcript sections
- Position tracking (remembers where you left off)

### How to Import a YouTube Video

1. Click **Import > Import from URL** in the main menu
2. Enter a YouTube video URL (e.g., `https://www.youtube.com/watch?v=VIDEO_ID`)
3. Click **OK** to import the video

### Working with YouTube Videos

Once imported, you can:

- **Play the video**: The video will appear in the top portion of the viewer
- **Read the transcript**: The transcript will appear in the bottom portion
- **Create extracts**: Select text in the transcript and click "Create Extract"
- **Track progress**: The application remembers your playback position between sessions
- **Search transcripts**: Use the search feature to find specific content in the transcript

### Requirements

- PyQt6-WebEngine (for video playback)
- youtube-transcript-api (for transcript retrieval)

### Limitations

- Transcripts are only available if the video creator has provided them or if YouTube has automatically generated them
- Some videos may have inaccurate auto-generated transcripts
- YouTube API rate limits may apply when retrieving many transcripts in a short period

## RSS Feeds

The RSS Feed feature allows you to subscribe to websites and blogs, automatically importing new articles into your knowledge base for review.

### Features

- Subscribe to multiple RSS feeds
- Automatically download new articles at specified intervals
- Configure each feed with custom settings
- Organize feeds by category
- Schedule articles for spaced repetition review
- Extract main content from cluttered web pages

### Managing RSS Feeds

To manage your RSS feeds:

1. Navigate to **Tools > Manage RSS Feeds**
2. The RSS Feed Manager will open with the following options:
   - **Add Feed**: Subscribe to a new RSS feed
   - **Edit Feed**: Modify settings for an existing feed
   - **Delete Feed**: Remove a feed (with option to delete associated documents)
   - **Test Feed**: Test if a feed URL is valid and can be parsed
   - **Refresh Feeds**: Manually check for new content in all feeds
   - **Import All**: Force import of unprocessed feed entries

### Adding a New Feed

1. Click the **Add Feed** button
2. Enter the feed details:
   - **URL**: The RSS feed URL
   - **Title**: A name for the feed (auto-filled if available from the feed)
   - **Category**: Where to store articles from this feed
   - **Check Frequency**: How often to check for new content (in minutes)
   - **Auto Import**: Whether to automatically import new items
   - **Max Items**: Maximum number of articles to keep per feed

### RSS Feed Settings

You can configure global RSS settings in the application settings dialog:

- **Default Check Frequency**: How often to check feeds by default
- **Check Interval**: How often the application checks all feeds
- **Default Priority**: Priority level for imported articles
- **Default Auto Import**: Whether new feeds should auto-import by default
- **Default Max Items**: Default number of items to keep per feed

### How RSS Content is Processed

When new articles are found in a feed:

1. The article's full content is downloaded
2. Main article content is extracted from the page (removing ads, navigation, etc.)
3. The content is saved as an HTML document in your knowledge base
4. The document is linked to its source feed for tracking

## ArXiv Papers

The ArXiv import feature allows you to search for and import scientific papers directly from the ArXiv repository.

### Features

- Search the ArXiv database by keyword, author, category, or paper ID
- View paper metadata (title, authors, abstract, publication date)
- Import papers as PDF documents for further study
- Automatic metadata extraction

### Using ArXiv Import

To import papers from ArXiv:

1. Navigate to **Import > Import from ArXiv**
2. In the ArXiv dialog that appears:
   - Enter your search query (keywords, author names, paper IDs)
   - Select the maximum number of results to return
   - Choose the sort order (relevance, date)
   - Click **Search** to find matching papers

3. From the search results:
   - Review the paper titles, authors, and abstracts
   - Select papers you want to import
   - Choose a category for organization
   - Click **Import Selected** to add the papers to your knowledge base

### ArXiv Search Tips

- Use quotes for exact phrase matching: `"quantum computing"`
- Search by author: `author:Smith`
- Filter by category: `cat:cs.AI` (for Artificial Intelligence)
- Search by paper ID: `1903.00123`
- Combine terms with AND, OR: `neural networks AND deep learning`

### After Importing

Once an ArXiv paper is imported:

- It's stored as a PDF document in your knowledge base
- Metadata (title, authors, abstract) is saved with the document
- You can create extracts, highlights, and annotations
- The paper can be included in your spaced repetition schedule

## Other Import Options

In addition to YouTube, RSS, and ArXiv, Incrementum supports:

- **File Import**: Import PDFs, EPUBs, text files, and other document formats
- **URL Import**: Import articles and web pages by URL
- **Web Browser**: Browse the web within Incrementum and save pages
- **Knowledge Base Import/Export**: Transfer knowledge between instances

Each import method is designed to facilitate the incorporation of diverse content types into your knowledge base, supporting comprehensive learning and review. 