# Audio Implementation Technical Documentation

This document provides technical details about how audio file support is implemented in Incrementum.

## Architecture Overview

The audio support feature consists of the following components:

1. **AudioHandler**: A document handler for processing audio files (mp3, wav, etc.)
2. **AudioPlayerWidget**: A Qt widget for playing audio files with position tracking
3. **Document View Integration**: Extensions to the document view for displaying the audio player

## Component Details

### AudioHandler

Located in `core/document_processor/handlers/audio_handler.py`, this class extends the `DocumentHandler` base class and provides:

- Metadata extraction from audio files using ffmpeg
- Content extraction (limited to basic metadata, as audio doesn't have text content)
- URL download capabilities for audio files

Key methods:
- `extract_metadata(file_path)`: Extracts metadata like title, artist, duration
- `extract_content(file_path)`: Returns basic metadata about the audio
- `download_from_url(url)`: Downloads an audio file from a URL

The handler supports multiple audio formats including MP3, WAV, OGG, FLAC, M4A, and AAC.

### AudioPlayerWidget

Located in `ui/load_audio_helper.py`, this widget provides a UI for playing audio files with:

- Playback controls (play/pause, seek, speed control)
- Position tracking and automatic saving of position
- Display of audio metadata (title, artist, duration)

The widget is built on top of Qt's multimedia framework, using:
- `QMediaPlayer` for audio playback
- `QAudioOutput` for audio output
- Qt signals and slots for handling events

Key features:
- Position auto-saving when significant progress is made (30+ seconds)
- Manual position saving
- Playback speed adjustment (0.75x to 2.0x)
- Skip forward/backward 15 seconds
- Position display and manual position entry

### Document View Integration

The document view is extended to handle audio files by adding:

1. A new content type detection in `load_document` method
2. A `_load_audio` method that:
   - Creates an `AudioPlayerWidget`
   - Sets up the widget with the document and position
   - Adds the widget to the content layout

## Data Model

Audio files use the existing `Document` model in the database with:

- `content_type` set to the specific audio format (mp3, wav, etc.)
- `position` storing the playback position in seconds
- Standard fields like `title`, `author`, etc. populated from audio metadata

## Implementation Challenges

1. **Metadata Extraction**: Audio files can have inconsistent metadata. The implementation uses ffmpeg's `ffprobe` to reliably extract this data when available.

2. **Position Tracking**: Similar to YouTube videos, audio requires careful position tracking to ensure the user can resume where they left off. The implementation includes:
   - Auto-saving when position changes significantly
   - Manual saving option
   - Position saving on player close/application exit

3. **Performance**: Audio files can be large. The player loads audio efficiently without loading the entire file into memory.

## Testing

The audio implementation can be tested by:

1. Importing different audio file formats
2. Checking metadata extraction accuracy
3. Verifying position saving across application restarts
4. Testing playback speed controls

## Dependencies

The implementation requires:
- `PyQt6-Multimedia` for audio playback capabilities
- `ffmpeg` (system dependency) for metadata extraction

## Future Enhancements

Potential enhancements to consider:

1. **Waveform visualization**: Adding a visual representation of the audio waveform
2. **Audio bookmarks**: Allowing users to bookmark specific positions
3. **Audio transcription**: Integration with speech-to-text to generate transcripts
4. **Playlist support**: Managing multiple audio files in sequence

## Limitations

Current limitations to be aware of:

1. DRM-protected audio files may not play correctly
2. Very large audio files (several hours) may have performance issues on slower systems
3. Some audio codecs might require additional system libraries

## Integration Points

The audio feature integrates with:

- The document queueing system (like other document types)
- The extract creation system (allowing timestamped extracts)
- The spaced repetition algorithm (treating audio files as reviewable documents)

## Code Example: Setting up the AudioPlayerWidget

```python
# Example of how the AudioPlayerWidget is created and set up
from ui.load_audio_helper import setup_audio_player

# Document is retrieved from database
document = self.db_session.query(Document).filter_by(id=document_id).first()

# Initial position (0 or from document)
target_position = document.position if document.position else 0

# Set up player
audio_player = setup_audio_player(
    parent_widget,
    document,
    db_session,
    target_position
)

# Add to layout
layout.addWidget(audio_player)
``` 