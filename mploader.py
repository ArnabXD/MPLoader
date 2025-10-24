#!/usr/bin/env python3
"""
MPLoader - YouTube to JioSaavn Music Downloader

A robust music downloader that extracts metadata from YouTube videos/playlists
and downloads matching high-quality tracks from JioSaavn with comprehensive
ID3 tagging and parallel processing support.

Author: Arnab Paryali
License: MIT
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

import requests
import yt_dlp
from mutagen.id3 import APIC, COMM, ID3, TALB, TCOM, TCON, TDRC, TIT2, TPE1, TPE2, TPUB
from mutagen.mp3 import MP3
from pydub import AudioSegment

# Module-level constants
DEFAULT_OUTPUT_DIR = "downloads"
DEFAULT_WORKERS = 3
DEFAULT_BITRATE = "320k"
HIGHEST_QUALITY = "320kbps"
IMAGE_QUALITY_PREFERENCE = "500x500"
CHUNK_SIZE = 8192

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(threadName)s] - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Thread synchronization
print_lock = threading.Lock()


class APIError(Exception):
    """Raised when API requests fail."""
    pass


class DownloadError(Exception):
    """Raised when download operations fail."""
    pass


class JioSaavnClient:
    """
    Client for interacting with JioSaavn API.

    Handles song search and metadata retrieval from JioSaavn's public API.
    """

    SEARCH_ENDPOINT = "https://saavn.sumit.co/api/search"
    SONG_ENDPOINT = "https://saavn.sumit.co/api/songs"

    def __init__(self) -> None:
        """Initialize the JioSaavn API client."""
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

    def search_song(self, query: str) -> Optional[Dict]:
        """
        Search for a song on JioSaavn.

        Args:
            query: Search query string

        Returns:
            Dictionary containing song metadata if found, None otherwise
        """
        try:
            response = self.session.get(self.SEARCH_ENDPOINT, params={"query": query})
            response.raise_for_status()
            data = response.json()

            if not data.get("success"):
                logger.warning(f"Search failed for query: {query}")
                return None

            # Try to get song from results
            songs = data.get("data", {}).get("songs", {}).get("results", [])
            if songs:
                return songs[0]

            # Fallback to top query result
            top_query = data.get("data", {}).get("topQuery", {}).get("results", [])
            if top_query:
                return top_query[0]

            logger.warning(f"No results found for query: {query}")
            return None

        except requests.RequestException as e:
            logger.error(f"Network error while searching: {e}")
            return None
        except (KeyError, ValueError) as e:
            logger.error(f"Error parsing search results: {e}")
            return None

    def get_song_details(self, song_id: str) -> Optional[Dict]:
        """
        Retrieve detailed song information including download URLs.

        Args:
            song_id: JioSaavn song identifier

        Returns:
            Dictionary containing detailed song metadata, or None if not found
        """
        try:
            url = f"{self.SONG_ENDPOINT}/{song_id}"
            response = self.session.get(url)
            response.raise_for_status()
            data = response.json()

            if not data.get("success"):
                logger.error(f"Failed to retrieve song details for ID: {song_id}")
                return None

            songs = data.get("data", [])
            return songs[0] if songs else None

        except requests.RequestException as e:
            logger.error(f"Network error while fetching song details: {e}")
            return None
        except (KeyError, ValueError, IndexError) as e:
            logger.error(f"Error parsing song details: {e}")
            return None


class YouTubeMetadataExtractor:
    """
    Extracts metadata from YouTube videos and playlists.

    Uses yt-dlp to extract video/playlist information without downloading.
    """

    # Patterns to clean from YouTube titles
    CLEANUP_PATTERNS = [
        r"\(Official.*?\)",
        r"\[Official.*?\]",
        r"\(Audio\)",
        r"\[Audio\]",
        r"\(Lyric.*?\)",
        r"\[Lyric.*?\]",
        r"\(.*?Video\)",
        r"\[.*?Video\]",
        r"\bHD\b",
        r"\bHQ\b",
        r"\b4K\b",
        r"\|.*$"
    ]

    def __init__(self) -> None:
        """Initialize the YouTube metadata extractor."""
        self.ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True
        }

    def extract_metadata(self, url: str) -> List[Dict]:
        """
        Extract metadata from a YouTube URL.

        Args:
            url: YouTube video or playlist URL

        Returns:
            List of dictionaries containing track metadata
        """
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

                if "entries" in info:
                    # Handle playlist
                    tracks = [
                        {
                            "title": entry.get("title", ""),
                            "uploader": entry.get("uploader", ""),
                            "url": entry.get("url", ""),
                            "id": entry.get("id", "")
                        }
                        for entry in info["entries"]
                        if entry
                    ]
                    logger.info(f"Found {len(tracks)} tracks in playlist")
                    return tracks
                else:
                    # Handle single video
                    return [{
                        "title": info.get("title", ""),
                        "uploader": info.get("uploader", ""),
                        "url": url,
                        "id": info.get("id", "")
                    }]

        except Exception as e:
            logger.error(f"Error extracting YouTube metadata: {e}")
            return []

    @classmethod
    def clean_title(cls, title: str) -> str:
        """
        Clean YouTube title for better search results.

        Removes common patterns like [Official Video], (Audio), etc.

        Args:
            title: Raw YouTube video title

        Returns:
            Cleaned title string
        """
        cleaned = title
        for pattern in cls.CLEANUP_PATTERNS:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

        # Clean up extra whitespace and trailing dashes
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        cleaned = re.sub(r"\s*-\s*$", "", cleaned)

        return cleaned


class AudioProcessor:
    """
    Handles audio downloading, conversion, and metadata tagging.

    Downloads audio files, converts to MP3, and embeds comprehensive ID3 tags.
    """

    def __init__(self, session: requests.Session) -> None:
        """
        Initialize the audio processor.

        Args:
            session: Requests session for downloads
        """
        self.session = session

    def download_audio(self, url: str, output_path: Path) -> bool:
        """
        Download audio file from URL.

        Args:
            url: Download URL
            output_path: Path where file should be saved

        Returns:
            True if successful, False otherwise
        """
        try:
            response = self.session.get(url, stream=True)
            response.raise_for_status()

            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)

            logger.info(f"Downloaded: {output_path.name}")
            return True

        except requests.RequestException as e:
            logger.error(f"Download failed: {e}")
            return False
        except IOError as e:
            logger.error(f"File write error: {e}")
            return False

    def convert_to_mp3(self, input_path: Path, output_path: Path) -> bool:
        """
        Convert audio file to MP3 format.

        Args:
            input_path: Path to input audio file
            output_path: Path for output MP3 file

        Returns:
            True if successful, False otherwise
        """
        try:
            audio = AudioSegment.from_file(str(input_path))
            audio.export(
                str(output_path),
                format="mp3",
                bitrate=DEFAULT_BITRATE,
                parameters=["-q:a", "0"]  # Highest quality VBR
            )

            logger.info(f"Converted to MP3: {output_path.name}")
            return True

        except Exception as e:
            logger.error(f"Conversion failed: {e}")
            return False

    def embed_metadata(self, file_path: Path, metadata: Dict) -> bool:
        """
        Embed comprehensive ID3 metadata into MP3 file.

        Args:
            file_path: Path to MP3 file
            metadata: Dictionary containing metadata fields

        Returns:
            True if successful, False otherwise
        """
        try:
            audio = MP3(str(file_path), ID3=ID3)

            # Initialize ID3 tags if needed
            try:
                audio.add_tags()
            except Exception:
                pass  # Tags already exist

            # Basic metadata
            self._add_text_frame(audio, TIT2, metadata.get("title"))
            self._add_text_frame(audio, TPE1, metadata.get("artist"))
            self._add_text_frame(audio, TALB, metadata.get("album"))
            self._add_text_frame(audio, TDRC, metadata.get("year"))

            # Extended metadata
            self._add_text_frame(audio, TPE2, metadata.get("album_artist"))
            self._add_text_frame(audio, TCON, metadata.get("language", "").title())
            self._add_text_frame(audio, TCOM, metadata.get("composers"))
            self._add_text_frame(audio, TPUB, metadata.get("label"))

            # Comments
            self._add_comment(audio, "Copyright", metadata.get("copyright"))
            self._add_comment(audio, "URL", metadata.get("url"))

            # Duration
            if metadata.get("duration"):
                duration_str = self._format_duration(metadata["duration"])
                self._add_comment(audio, "Duration", duration_str)

            # Album artwork
            if metadata.get("image_url"):
                self._embed_artwork(audio, metadata["image_url"])

            audio.save()
            logger.info(f"Embedded metadata: {file_path.name}")
            return True

        except Exception as e:
            logger.error(f"Metadata embedding failed: {e}")
            return False

    def _add_text_frame(self, audio: MP3, frame_class, text: Optional[str]) -> None:
        """Add text frame to ID3 tags if text is provided."""
        if text:
            audio.tags.add(frame_class(encoding=3, text=str(text)))

    def _add_comment(self, audio: MP3, description: str, text: Optional[str]) -> None:
        """Add comment frame to ID3 tags if text is provided."""
        if text:
            audio.tags.add(COMM(encoding=3, lang="eng", desc=description, text=text))

    def _format_duration(self, seconds: int) -> str:
        """Format duration in seconds to MM:SS format."""
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}:{secs:02d}"

    def _embed_artwork(self, audio: MP3, image_url: str) -> None:
        """Download and embed album artwork."""
        try:
            response = self.session.get(image_url)
            if response.status_code == 200:
                audio.tags.add(APIC(
                    encoding=3,
                    mime="image/jpeg",
                    type=3,
                    desc="Cover",
                    data=response.content
                ))
        except Exception as e:
            logger.debug(f"Failed to embed artwork: {e}")


class MusicDownloader:
    """
    Main orchestrator for music download operations.

    Coordinates YouTube metadata extraction, JioSaavn search,
    and audio processing with multi-threaded execution.
    """

    def __init__(self, output_dir: str = DEFAULT_OUTPUT_DIR) -> None:
        """
        Initialize the music downloader.

        Args:
            output_dir: Directory where downloaded files will be saved
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

        self.jiosaavn_client = JioSaavnClient()
        self.youtube_extractor = YouTubeMetadataExtractor()
        self.audio_processor = AudioProcessor(self.jiosaavn_client.session)

    def process_url(self, url: str, max_workers: int = DEFAULT_WORKERS) -> None:
        """
        Process YouTube URL and download matching tracks.

        Args:
            url: YouTube video or playlist URL
            max_workers: Maximum number of parallel download workers
        """
        logger.info(f"Extracting metadata from: {url}")

        tracks = self.youtube_extractor.extract_metadata(url)
        if not tracks:
            logger.error("Could not extract any tracks from URL")
            return

        total_tracks = len(tracks)
        logger.info(f"Processing {total_tracks} track(s) with {max_workers} parallel workers")

        # Statistics tracking
        stats = {
            "success": 0,
            "failed": [],
            "cancelled": []
        }

        # Execute downloads in parallel
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="Worker") as executor:
            future_to_track = {
                executor.submit(self._process_single_track, track): (i, track)
                for i, track in enumerate(tracks, 1)
            }

            try:
                self._process_futures(future_to_track, total_tracks, stats)
            except KeyboardInterrupt:
                self._handle_interrupt(future_to_track, stats)
                raise

        # Display summary
        self._display_summary(total_tracks, stats)

    def _process_futures(
        self,
        future_to_track: Dict,
        total_tracks: int,
        stats: Dict
    ) -> None:
        """Process completed futures and update statistics."""
        for future in as_completed(future_to_track):
            track_num, track = future_to_track[future]
            try:
                if future.result():
                    stats["success"] += 1
                    logger.info(f"[{stats['success']}/{total_tracks}] Completed successfully")
                else:
                    stats["failed"].append(track.get("title", "Unknown"))
                    logger.warning(f"[{track_num}/{total_tracks}] Failed to process")
            except Exception as e:
                stats["failed"].append(track.get("title", "Unknown"))
                logger.error(f"[{track_num}/{total_tracks}] Exception: {e}")

    def _handle_interrupt(self, future_to_track: Dict, stats: Dict) -> None:
        """Handle keyboard interrupt gracefully."""
        logger.info("\n\nReceived Ctrl+C! Gracefully shutting down...")
        logger.info("Finishing current downloads, cancelling pending tasks...")

        # Cancel pending futures
        for future in future_to_track:
            if not future.running() and not future.done():
                if future.cancel():
                    _, track = future_to_track[future]
                    stats["cancelled"].append(track.get("title", "Unknown"))

        logger.info(f"Cancelled {len(stats['cancelled'])} pending tasks")
        logger.info("Waiting for running tasks to complete...")

    def _display_summary(self, total: int, stats: Dict) -> None:
        """Display download summary."""
        logger.info(f"\n{'='*60}")
        logger.info("Download Summary:")
        logger.info(
            f"Total: {total} | "
            f"Success: {stats['success']} | "
            f"Failed: {len(stats['failed'])} | "
            f"Cancelled: {len(stats['cancelled'])}"
        )

        if stats["failed"]:
            logger.info("\nFailed tracks:")
            for track in stats["failed"]:
                logger.info(f"  - {track}")

        if stats["cancelled"]:
            logger.info("\nCancelled tracks:")
            for track in stats["cancelled"]:
                logger.info(f"  - {track}")

        logger.info(f"{'='*60}")

    def _process_single_track(self, track_info: Dict) -> bool:
        """
        Process a single track: search, download, convert, tag.

        Args:
            track_info: Dictionary containing track metadata from YouTube

        Returns:
            True if processing succeeded, False otherwise
        """
        try:
            # Clean title and search
            cleaned_title = self.youtube_extractor.clean_title(track_info["title"])
            logger.info(f"Processing: {cleaned_title}")

            # Search on JioSaavn
            search_result = self.jiosaavn_client.search_song(cleaned_title)
            if not search_result or not search_result.get("id"):
                logger.warning(f"Not found on JioSaavn: {cleaned_title}")
                return False

            # Get detailed song information
            song_details = self.jiosaavn_client.get_song_details(search_result["id"])
            if not song_details:
                logger.warning(f"Could not retrieve song details: {cleaned_title}")
                return False

            # Extract download URL
            download_url = self._get_download_url(song_details)
            if not download_url:
                logger.warning(f"No download URL available: {cleaned_title}")
                return False

            # Prepare file paths
            filename = self._create_filename(song_details)
            temp_file = self.output_dir / f"{filename}.temp"
            output_file = self.output_dir / f"{filename}.mp3"

            # Skip if already exists
            if output_file.exists():
                logger.info(f"Already exists: {output_file.name}")
                return True

            # Download and process
            if not self._download_and_convert(download_url, temp_file, output_file):
                return False

            # Embed metadata
            metadata = self._extract_metadata(song_details)
            self.audio_processor.embed_metadata(output_file, metadata)

            logger.info(f"Successfully processed: {output_file.name}")
            return True

        except Exception as e:
            logger.error(f"Error processing track: {e}")
            return False

    def _get_download_url(self, song_details: Dict) -> Optional[str]:
        """Extract highest quality download URL from song details."""
        download_links = song_details.get("downloadUrl", [])
        if not download_links:
            return None

        # Prefer 320kbps quality
        for link in download_links:
            if link.get("quality") == HIGHEST_QUALITY:
                return link.get("url")

        # Fallback to highest available
        return download_links[-1].get("url")

    def _create_filename(self, song_details: Dict) -> str:
        """Create sanitized filename from song details."""
        artists = song_details.get("artists", {}).get("primary", [])
        artist_names = ", ".join(a.get("name", "") for a in artists) or "Unknown"

        title = song_details.get("name", "Unknown")
        filename = f"{title} - {artist_names}"

        # Sanitize filename
        filename = re.sub(r'[<>:"/\\|?*]', "", filename)
        filename = filename[:200].strip()

        return filename

    def _download_and_convert(
        self,
        download_url: str,
        temp_file: Path,
        output_file: Path
    ) -> bool:
        """Download audio and convert to MP3."""
        try:
            # Download
            if not self.audio_processor.download_audio(download_url, temp_file):
                return False

            # Convert
            if not self.audio_processor.convert_to_mp3(temp_file, output_file):
                temp_file.unlink(missing_ok=True)
                return False

            # Cleanup
            temp_file.unlink(missing_ok=True)
            return True

        except Exception as e:
            logger.error(f"Download/conversion error: {e}")
            temp_file.unlink(missing_ok=True)
            return False

    def _extract_metadata(self, song_details: Dict) -> Dict:
        """Extract metadata dictionary from song details."""
        # Get image URL
        images = song_details.get("image", [])
        image_url = None
        if images:
            for img in images:
                if img.get("quality") == IMAGE_QUALITY_PREFERENCE:
                    image_url = img.get("url")
                    break
            if not image_url:
                image_url = images[-1].get("url")

        # Get artist information
        artists = song_details.get("artists", {})
        primary_artists = artists.get("primary", [])
        all_artists = artists.get("all", [])

        artist_names = ", ".join(a.get("name", "") for a in primary_artists) or "Unknown"
        composers = ", ".join(
            a.get("name", "") for a in all_artists if a.get("role") == "lyricist"
        )
        album_artists = ", ".join(
            a.get("name", "") for a in all_artists
            if a.get("role") in ["music", "composer"]
        )

        # Get album information
        album = song_details.get("album", {})
        album_name = album.get("name") if isinstance(album, dict) else album

        return {
            "title": song_details.get("name"),
            "artist": artist_names,
            "album": album_name,
            "year": song_details.get("year"),
            "image_url": image_url,
            "album_artist": album_artists or artist_names,
            "language": song_details.get("language"),
            "composers": composers or None,
            "label": song_details.get("label"),
            "copyright": song_details.get("copyright"),
            "url": song_details.get("url"),
            "duration": song_details.get("duration")
        }


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Download music from JioSaavn based on YouTube video/playlist metadata",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "https://www.youtube.com/watch?v=VIDEO_ID"
  %(prog)s "https://www.youtube.com/playlist?list=PLAYLIST_ID" -w 5
  %(prog)s "YOUTUBE_URL" -o ~/Music -w 3
        """
    )

    parser.add_argument(
        "url",
        help="YouTube video or playlist URL"
    )

    parser.add_argument(
        "-o", "--output",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})"
    )

    parser.add_argument(
        "-w", "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"Number of parallel download workers (default: {DEFAULT_WORKERS})"
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    return parser.parse_args()


def main() -> None:
    """Main entry point for the application."""
    args = parse_arguments()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    try:
        downloader = MusicDownloader(output_dir=args.output)
        downloader.process_url(args.url, max_workers=args.workers)
    except KeyboardInterrupt:
        logger.info("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()