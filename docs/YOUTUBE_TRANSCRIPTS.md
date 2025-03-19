# YouTube Transcript Support

Incrementum now supports extracting and working with YouTube video transcripts. This feature allows you to:

1. Import YouTube videos with their transcripts
2. View transcripts alongside videos
3. Create knowledge extracts directly from transcripts

## Requirements

This feature requires:

- PyQt6-WebEngine (for video playback)
- youtube-transcript-api (for transcript retrieval)

You can install the required dependencies by running:

```bash
pip install youtube-transcript-api
```

## Using the YouTube Transcript Feature

### Importing YouTube Videos

1. Click **Import > Import from URL** in the main menu
2. Enter a YouTube video URL (e.g., `https://www.youtube.com/watch?v=VIDEO_ID`)
3. Click **OK** to import the video

If a transcript is available for the video, it will be automatically fetched and saved with the video metadata.

### Viewing Transcripts

When you open a YouTube video document that has a transcript available:

1. The video player will appear in the top portion of the view
2. The transcript will appear in the bottom portion
3. You can adjust the split between video and transcript by dragging the splitter

### Creating Extracts from Transcripts

To create extracts from the transcript:

1. Select the text in the transcript that you want to extract
2. Click the **Create Extract from Selection** button at the top of the transcript view
3. Alternatively, right-click on the selected text and choose **Create Extract**

The extract will be created and added to your knowledge base, just like extracts from other document types.

## Features

- **Automatic Transcript Detection**: Incrementum automatically detects and retrieves available transcripts for YouTube videos
- **Multiple Language Support**: If multiple languages are available, English is prioritized by default
- **Extract Context**: When creating extracts, surrounding text is automatically included as context
- **Position Tracking**: The extract's position in the transcript is saved for future reference

## Limitations

- Transcripts are only available if the video creator has provided them or if YouTube has automatically generated them
- Some videos may have inaccurate auto-generated transcripts
- The YouTube API has rate limits that may affect transcript retrieval for many videos in a short period

## API Key (Optional)

For enhanced functionality, you can set the `YOUTUBE_API_KEY` environment variable with your YouTube Data API key:

```bash
export YOUTUBE_API_KEY=your_api_key_here
```

This allows for better transcript detection and management but is not required for basic functionality. 