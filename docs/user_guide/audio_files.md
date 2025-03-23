# Audio Files in Incrementum

Incrementum supports audio files for incremental listening, allowing you to process audio content (such as podcasts, lectures, audiobooks, and music) using the same spaced repetition system as other content.

## Supported Audio Formats

The following audio formats are supported:

- MP3 (.mp3)
- WAV (.wav)
- OGG (.ogg)
- FLAC (.flac)
- M4A (.m4a)
- AAC (.aac)

## Prerequisites

To use the audio file feature, you need to have **ffmpeg** installed on your system. 

### Installing ffmpeg

- **Linux**: `sudo apt install ffmpeg` (Ubuntu/Debian) or `sudo pacman -S ffmpeg` (Arch)
- **macOS**: `brew install ffmpeg`
- **Windows**: Download from [ffmpeg.org](https://ffmpeg.org/download.html) or use Chocolatey: `choco install ffmpeg`

## Adding Audio Files to Incrementum

You can add audio files to Incrementum in the same way as other documents:

1. Click on **File** > **Import Document** in the menu
2. Select an audio file from your computer
3. Choose a category (optional)
4. Click **Import**

Alternatively, you can drag and drop audio files directly into the main window.

## Incremental Listening

Once imported, audio files appear in your queue like any other document. When it's time to review an audio file:

1. The audio player will automatically load and display the file information
2. The player will resume from where you left off in your previous session
3. Use the playback controls to listen to the content

### Audio Player Features

- **Play/Pause**: Start or pause playback
- **Rewind/Forward**: Skip backward or forward by 15 seconds
- **Playback Speed**: Adjust listening speed from 0.75x to 2.0x
- **Position Tracking**: Your listening position is automatically saved as you progress
- **Manual Position Control**: You can manually input a specific time position

## Creating Extracts from Audio

While listening to audio content, you can create extracts to save important parts:

1. Pause the audio at the relevant point
2. Use the **Create Extract** button in the Extracts panel
3. Enter a description or transcribe the audio segment in the extract text
4. Add tags or notes as needed
5. Save the extract

The extract will include a timestamp reference to the audio position.

## Best Practices for Incremental Listening

- **Break up longer audio**: For long audio files like podcasts or lectures, consider creating multiple extracts at key points
- **Use playback speed adjustment**: Increase the speed for review or slow it down for complex content
- **Save positions manually**: While positions are auto-saved, you can manually save at significant points
- **Take notes**: Use the extracts feature to capture your thoughts about the audio

## Troubleshooting

If you encounter issues with audio playback:

- Ensure ffmpeg is installed and accessible from your system path
- Check that the audio file is not corrupted
- Verify that the file format is one of the supported types
- Make sure your system has the necessary audio codecs installed

## Integration with Spaced Repetition

Audio files use the same spaced repetition algorithms as other documents in Incrementum. As you review audio files, the system will adjust the scheduling based on your configured settings.

---

For technical information on the audio file implementation, see the [developer documentation](/docs/developer/audio_implementation.md). 