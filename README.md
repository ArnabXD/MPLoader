# MPLoader

> YouTube to JioSaavn Music Downloader with parallel processing

Download high-quality music from JioSaavn based on YouTube video/playlist metadata with comprehensive ID3 tagging.

## Features

- 🎵 YouTube playlists and single videos
- 🎨 320kbps MP3 with album artwork
- 🏷️ Full ID3 tags (artist, album, composer, label, copyright)
- ⚡ Parallel downloads (3 workers default)
- 🛑 Graceful Ctrl+C handling

## Prerequisites

- Python 3.7+
- FFmpeg

**Install FFmpeg:**
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg
```

## Installation

```bash
uv sync
```

## Usage

```bash
# Single video
uv run mploader.py "YOUTUBE_URL"

# Playlist with options
uv run mploader.py "YOUTUBE_URL" -o ~/Music -w 5 -v
```

**Options:**
- `-o` Output directory (default: `downloads`)
- `-w` Parallel workers (default: `3`)
- `-v` Verbose logging

## License

MIT License