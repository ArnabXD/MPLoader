# MPLoader

> YouTube to JioSaavn Music Downloader with parallel processing and comprehensive ID3 tagging

MPLoader extracts metadata from YouTube videos/playlists and downloads matching high-quality tracks from JioSaavn with proper metadata and album artwork.

## Features

- 🎵 Download from YouTube playlists or individual videos
- 🔍 Automatic song matching via JioSaavn search
- 🎨 320kbps MP3 with embedded album artwork
- 🏷️ Comprehensive ID3 tags (artist, album, year, composer, label, copyright)
- ⚡ Parallel downloads (3 workers by default)
- 🛑 Graceful interrupt handling (Ctrl+C)
- ✅ Skip already downloaded tracks

## Prerequisites

- Python 3.7+
- FFmpeg (required for audio conversion)

### Install FFmpeg

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt install ffmpeg
```

**Windows:**
Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd mploader

# Install with uv (recommended)
uv sync

# Or with pip
pip install -r requirements.txt
```

## Usage

### Basic Usage

```bash
# Single video
uv run mploader.py "https://www.youtube.com/watch?v=VIDEO_ID"

# Playlist
uv run mploader.py "https://www.youtube.com/playlist?list=PLAYLIST_ID"
```

### Advanced Options

```bash
# Custom output directory
uv run mploader.py "YOUTUBE_URL" -o ~/Music

# More parallel workers (faster downloads)
uv run mploader.py "YOUTUBE_URL" -w 5

# Verbose logging
uv run mploader.py "YOUTUBE_URL" -v

# All together
uv run mploader.py "YOUTUBE_URL" -o ~/Music -w 5 -v
```

### Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `url` | YouTube video or playlist URL | Required |
| `-o, --output` | Output directory | `downloads` |
| `-w, --workers` | Number of parallel workers | `3` |
| `-v, --verbose` | Enable verbose logging | `false` |

## Output

Downloaded files are saved as:
```
downloads/
├── Song Title - Artist Name.mp3
├── Another Song - Artist.mp3
└── ...
```

Each MP3 includes:
- Title, Artist, Album, Year
- Album Artist, Composers, Label
- Language/Genre, Copyright
- 500x500px Album Artwork
- Duration metadata

## How It Works

1. Extracts metadata from YouTube (title, uploader)
2. Cleans title (removes `[Official Video]`, `(Audio)`, etc.)
3. Searches for matching track on JioSaavn
4. Downloads highest quality available (320kbps preferred)
5. Converts to MP3 format
6. Embeds comprehensive ID3 tags with artwork
7. Saves to output directory

## Graceful Shutdown

Press **Ctrl+C** to stop:
- Completes currently downloading tracks
- Cancels pending tasks
- Shows summary of completed/failed/cancelled tracks

## Troubleshooting

**Error: "ffmpeg not found"**
→ Install FFmpeg (see Prerequisites)

**Error: "No results found"**
→ Track may not be available on JioSaavn or title needs manual search

**Downloads are slow**
→ Try increasing workers: `-w 5`

## Cleaning Unwanted Files

Remove covers, remixes, lofi versions, etc.:

```bash
# Preview what will be deleted
find downloads -type f -name "*.mp3" | grep -iE '(lofi|cover|remix|acoustic|live|slowed)'

# Delete them
find downloads -type f -name "*.mp3" | grep -iE '(lofi|cover|remix|acoustic|live|slowed)' | xargs rm
```

## Legal Notice

This tool is for educational purposes only. Respect copyright laws and terms of service. Only download content you have rights to access.

## License

MIT License - see LICENSE file for details

## Author

Arnab Paryali

## Contributing

Contributions welcome! Please open an issue or submit a pull request.