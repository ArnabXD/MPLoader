# MPLoader - YouTube to JioSaavn Music Downloader

Download high-quality music from JioSaavn based on YouTube video or playlist metadata.

## Features

- Extract metadata from YouTube videos and playlists
- Search and download matching tracks from JioSaavn
- Convert to MP3 format with 320kbps bitrate for broad device compatibility
- Add proper ID3 tags (title, artist, album, year, album art)
- Handle both single videos and entire playlists
- Skip already downloaded tracks

## Requirements

- Python 3.7 or higher
- FFmpeg (required by pydub for audio conversion)

### Installing FFmpeg

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install ffmpeg
```

**Windows:**
Download from https://ffmpeg.org/download.html and add to PATH

## Installation

1. Clone or download this repository
2. Install Python dependencies:

```bash
pip install -r requirements.txt
```

## Usage

### Basic usage (single video):
```bash
python mploader.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

### Download entire playlist:
```bash
python mploader.py "https://www.youtube.com/playlist?list=PLAYLIST_ID"
```

### Specify output directory:
```bash
python mploader.py "YOUTUBE_URL" -o /path/to/output
```

### Enable verbose logging:
```bash
python mploader.py "YOUTUBE_URL" -v
```

## How It Works

1. Extracts video/playlist metadata from YouTube (title, artist)
2. Cleans up the title (removes tags like [Official Video], (Audio), etc.)
3. Searches for the track on JioSaavn
4. Downloads the audio file (highest quality available)
5. Converts to MP3 format with 320kbps bitrate
6. Adds ID3 metadata tags and album artwork
7. Saves to the output directory

## Output

Downloaded files are saved as:
```
downloads/
├── Song Title - Artist Name.mp3
├── Another Song - Artist.mp3
└── ...
```

Each MP3 file includes:
- Title
- Artist
- Album
- Year
- Album artwork (embedded)

## Limitations

- Requires active internet connection
- Track matching depends on JioSaavn's search results
- Some tracks may not be available on JioSaavn
- Download speeds depend on JioSaavn's servers

## Troubleshooting

**Error: "ffmpeg not found"**
- Install FFmpeg using the instructions above

**Error: "No results found"**
- The track may not be available on JioSaavn
- Try a different search query

**Error: "Could not get download URL"**
- JioSaavn's API may have changed
- Try again later

## Legal Notice

This tool is for educational purposes only. Please respect copyright laws and terms of service of YouTube and JioSaavn. Only download content you have the right to access.

## License

MIT License