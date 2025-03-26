# RSS Feed Management

## Overview

Incrementum includes a powerful RSS feed reader that allows you to automatically import content from your favorite websites and blogs directly into your knowledge database. This feature enables you to:

- Subscribe to and manage multiple RSS feeds
- Automatically check for new content at configurable intervals
- Import articles directly into your document library
- Organize imported content into categories
- Read content within the application

## Accessing the RSS Feature

The RSS feed functionality can be accessed from the main menu:

1. Go to **Tools > Manage RSS Feeds**
2. The RSS Feed Manager dialog will open, showing your subscribed feeds and their entries

## Managing Feeds

### Adding a New Feed

To add a new RSS feed:

1. Open the RSS Feed Manager (**Tools > Manage RSS Feeds**)
2. Click the **Add Feed** button
3. In the dialog that appears, enter:
   - **Title**: A name for the feed (this will be auto-filled if you test the feed)
   - **Feed URL**: The URL of the RSS feed (e.g., `https://example.com/feed/`)
   - **Category**: (Optional) Select a category where imported articles will be stored
   - **Check frequency**: How often Incrementum should check for new content (in minutes)
   - **Automatically import new items**: Toggle to automatically import new entries
   - **Max items to keep**: Set a limit to prevent unlimited growth (0 keeps all items)
4. Click **Test Feed** to verify the feed works correctly
5. Click **OK** to add the feed

### Editing a Feed

To edit an existing feed:

1. Select the feed in the RSS Feed Manager
2. Right-click and select **Edit Feed**
3. Modify any settings as needed
4. Click **OK** to save changes

### Deleting a Feed

To delete a feed:

1. Select the feed in the RSS Feed Manager
2. Right-click and select **Delete Feed**
3. Confirm the deletion
4. Choose whether to also delete documents imported from this feed

### Refreshing Feeds

To manually refresh feeds and check for new content:

- For a single feed: Right-click the feed and select **Refresh Feed**
- For all feeds: Click the **Refresh All** button

## Reading RSS Content

### Viewing Feed Entries

The RSS view provides a three-panel interface:

1. **Left panel**: List of your subscribed feeds
2. **Upper right panel**: Entries from the selected feed
3. **Lower right panel**: Preview of the selected entry

You can filter entries using the dropdown above the entries list:
- **All Entries**: Show all entries from the feed
- **Unread Only**: Show only entries you haven't read
- **Imported Only**: Show only entries that have been imported as documents

### Importing Content

To import an entry as a document:

1. Select the entry you want to import
2. Click the **Import** button at the top of the preview panel
3. The entry will be imported as a document in your library

You can also:
- Right-click an entry and select **Import Entry**
- Import all unread entries from a feed by right-clicking the feed and selecting **Import All Unread**

### Reading Imported Content

Once an entry is imported, you can read it directly in Incrementum:

1. Select the imported entry (it will show "Imported" in the Status column)
2. Click the **View** button to open the article

## Automatic Updates

Incrementum can automatically check for new feed content in the background:

1. The application periodically checks your feeds based on each feed's check frequency
2. If auto-import is enabled for a feed, new entries will be automatically imported
3. You can see the status of your feeds in the RSS Feed Manager

## Advanced Features

### Content Processing

When importing content from RSS feeds, Incrementum:

1. Downloads the full article content from the original website
2. Extracts the main article text, removing navigation, ads, and other clutter
3. Formats the content for better readability
4. Saves it as an HTML document in your library

### Feed Cleanup

To prevent your library from becoming cluttered:

1. Each feed can be configured with a "Max items to keep" setting
2. When this limit is reached, the oldest items will be automatically removed
3. Set this to 0 if you want to keep all items indefinitely

## Troubleshooting

### Feed Cannot Be Parsed

If you receive an error that a feed cannot be parsed:

1. Verify the URL is correct
2. Check that the URL points to an RSS or Atom feed, not a regular webpage
3. Try visiting the feed URL in your browser to see if it's accessible

### Content Not Displaying Correctly

If imported articles don't display correctly:

1. The website may be blocking content scrapers
2. Try visiting the original article through the source URL
3. Some sites may require a login or subscription for full content access

### Missing Images or Formatting

Some websites restrict access to images or may have complex formatting:

1. Most basic text content should import correctly
2. Complex layouts and interactive elements may not be preserved
3. Images hosted on the original site should display if you have internet access

## Best Practices

- Subscribe only to feeds you regularly read to avoid information overload
- Use categories to organize imported content by topic
- Set reasonable check frequencies (60 minutes is often sufficient)
- Configure "Max items to keep" based on your storage capacity and reading habits
- Periodically clean up old or irrelevant imported content 