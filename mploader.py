#!/usr/bin/env python3
"""
YouTube to JioSaavn Music Downloader
Downloads music from JioSaavn based on YouTube video/playlist metadata
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import List, Dict, Optional
import logging

import yt_dlp
import requests
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC, TDRC
from pydub import AudioSegment

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class JioSaavnAPI:
    """Handler for JioSaavn API interactions"""

    SEARCH_URL = "https://saavn.sumit.co/api/search"
    SONG_URL = "https://saavn.sumit.co/api/songs"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def search_song(self, query: str) -> Optional[Dict]:
        """Search for a song on JioSaavn"""
        try:
            params = {'query': query}
            response = self.session.get(self.SEARCH_URL, params=params)
            response.raise_for_status()
            data = response.json()

            # Check if search was successful
            if not data.get('success'):
                logger.warning(f"Search failed for: {query}")
                return None

            # Get top result from songs
            songs = data.get('data', {}).get('songs', {}).get('results', [])
            if songs:
                return songs[0]

            # Fallback to topQuery
            top_query = data.get('data', {}).get('topQuery', {}).get('results', [])
            if top_query:
                return top_query[0]

            logger.warning(f"No results found for: {query}")
            return None

        except Exception as e:
            logger.error(f"Error searching song: {e}")
            return None

    def get_song_details(self, song_id: str) -> Optional[Dict]:
        """Get detailed song information including download URLs"""
        try:
            # Song ID goes in the URL path, not as a parameter
            url = f"{self.SONG_URL}/{song_id}"
            response = self.session.get(url)
            response.raise_for_status()
            data = response.json()

            if not data.get('success'):
                logger.error(f"Failed to get song details for ID: {song_id}")
                return None

            songs = data.get('data', [])
            if songs and len(songs) > 0:
                return songs[0]

            return None

        except Exception as e:
            logger.error(f"Error getting song details: {e}")
            return None


class YouTubeExtractor:
    """Handler for YouTube metadata extraction"""

    def __init__(self):
        self.ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True
        }

    def extract_metadata(self, url: str) -> List[Dict]:
        """Extract metadata from YouTube video or playlist"""
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

                if 'entries' in info:
                    # Playlist
                    tracks = []
                    for entry in info['entries']:
                        if entry:
                            tracks.append({
                                'title': entry.get('title', ''),
                                'uploader': entry.get('uploader', ''),
                                'url': entry.get('url', ''),
                                'id': entry.get('id', '')
                            })
                    logger.info(f"Found {len(tracks)} tracks in playlist")
                    return tracks
                else:
                    # Single video
                    return [{
                        'title': info.get('title', ''),
                        'uploader': info.get('uploader', ''),
                        'url': url,
                        'id': info.get('id', '')
                    }]

        except Exception as e:
            logger.error(f"Error extracting YouTube metadata: {e}")
            return []

    @staticmethod
    def clean_title(title: str) -> str:
        """Clean YouTube title for better search results"""
        # Remove common patterns
        patterns = [
            r'\(Official.*?\)',
            r'\[Official.*?\]',
            r'\(Audio\)',
            r'\[Audio\]',
            r'\(Lyric.*?\)',
            r'\[Lyric.*?\]',
            r'\(.*?Video\)',
            r'\[.*?Video\]',
            r'HD',
            r'HQ',
            r'4K',
            r'\|.*$'
        ]

        cleaned = title
        for pattern in patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

        # Clean up extra spaces and dashes
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        cleaned = re.sub(r'\s*-\s*$', '', cleaned)

        return cleaned


class MusicDownloader:
    """Main downloader class"""

    def __init__(self, output_dir: str = "downloads"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

        self.jiosaavn = JioSaavnAPI()
        self.youtube = YouTubeExtractor()

    def download_audio(self, url: str, output_path: Path) -> bool:
        """Download audio file from URL"""
        try:
            response = self.jiosaavn.session.get(url, stream=True)
            response.raise_for_status()

            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            logger.info(f"Downloaded: {output_path.name}")
            return True

        except Exception as e:
            logger.error(f"Error downloading audio: {e}")
            return False

    def convert_to_mp3(self, input_path: Path, output_path: Path) -> bool:
        """Convert audio file to MP3 format"""
        try:
            audio = AudioSegment.from_file(str(input_path))
            audio.export(
                str(output_path),
                format='mp3',
                bitrate='320k',
                parameters=["-q:a", "0"]  # Highest quality
            )

            logger.info(f"Converted to MP3: {output_path.name}")
            return True

        except Exception as e:
            logger.error(f"Error converting to MP3: {e}")
            return False

    def add_metadata(self, file_path: Path, metadata: Dict) -> bool:
        """Add ID3 metadata to MP3 file"""
        try:
            audio = MP3(str(file_path), ID3=ID3)

            # Add ID3 tag if it doesn't exist
            try:
                audio.add_tags()
            except:
                pass

            # Add metadata
            if metadata.get('title'):
                audio.tags.add(TIT2(encoding=3, text=metadata['title']))

            if metadata.get('artist'):
                audio.tags.add(TPE1(encoding=3, text=metadata['artist']))

            if metadata.get('album'):
                audio.tags.add(TALB(encoding=3, text=metadata['album']))

            if metadata.get('year'):
                audio.tags.add(TDRC(encoding=3, text=str(metadata['year'])))

            # Add album art if available
            if metadata.get('image_url'):
                try:
                    img_response = self.jiosaavn.session.get(metadata['image_url'])
                    if img_response.status_code == 200:
                        audio.tags.add(
                            APIC(
                                encoding=3,
                                mime='image/jpeg',
                                type=3,
                                desc='Cover',
                                data=img_response.content
                            )
                        )
                except:
                    pass

            audio.save()
            logger.info(f"Added metadata to: {file_path.name}")
            return True

        except Exception as e:
            logger.error(f"Error adding metadata: {e}")
            return False

    def sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for filesystem"""
        # Remove invalid characters
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        # Limit length
        filename = filename[:200]
        return filename.strip()

    def process_track(self, track_info: Dict) -> bool:
        """Process a single track"""
        try:
            # Clean and search
            cleaned_title = self.youtube.clean_title(track_info['title'])
            logger.info(f"Processing: {cleaned_title}")

            # Search on JioSaavn
            search_result = self.jiosaavn.search_song(cleaned_title)
            if not search_result:
                logger.warning(f"Could not find on JioSaavn: {cleaned_title}")
                return False

            song_id = search_result.get('id')
            if not song_id:
                logger.warning(f"No song ID found for: {cleaned_title}")
                return False

            # Get song details with download links
            song_details = self.jiosaavn.get_song_details(song_id)
            if not song_details:
                logger.warning(f"Could not get song details: {cleaned_title}")
                return False

            # Get download URL - prefer highest quality
            download_links = song_details.get('downloadUrl', [])
            if not download_links:
                logger.warning(f"No download links found: {cleaned_title}")
                return False

            # Find highest quality link (320kbps or highest available)
            download_url = None
            for link in download_links:
                if link.get('quality') == '320kbps':
                    download_url = link.get('url')
                    break

            # Fallback to first available link
            if not download_url and download_links:
                download_url = download_links[-1].get('url')  # Usually highest quality is last

            if not download_url:
                logger.warning(f"Could not get download URL: {cleaned_title}")
                return False

            # Prepare filename
            artists = song_details.get('artists', {}).get('primary', [])
            artist_names = ', '.join([a.get('name', '') for a in artists]) if artists else 'Unknown'

            safe_title = self.sanitize_filename(
                f"{song_details.get('name', 'Unknown')} - {artist_names}"
            )
            temp_file = self.output_dir / f"{safe_title}.temp"
            output_file = self.output_dir / f"{safe_title}.mp3"

            # Skip if already exists
            if output_file.exists():
                logger.info(f"Already exists: {output_file.name}")
                return True

            # Download
            if not self.download_audio(download_url, temp_file):
                return False

            # Convert to MP3
            if not self.convert_to_mp3(temp_file, output_file):
                temp_file.unlink(missing_ok=True)
                return False

            # Clean up temp file
            temp_file.unlink(missing_ok=True)

            # Add metadata
            # Get image URL - prefer highest quality
            images = song_details.get('image', [])
            image_url = None
            if images:
                for img in images:
                    if img.get('quality') == '500x500':
                        image_url = img.get('url')
                        break
                if not image_url:
                    image_url = images[-1].get('url')  # Fallback to last (usually highest)

            metadata = {
                'title': song_details.get('name'),
                'artist': artist_names,
                'album': song_details.get('album', {}).get('name') if isinstance(song_details.get('album'), dict) else song_details.get('album'),
                'year': song_details.get('year'),
                'image_url': image_url
            }
            self.add_metadata(output_file, metadata)

            logger.info(f"Successfully processed: {output_file.name}")
            return True

        except Exception as e:
            logger.error(f"Error processing track: {e}")
            return False

    def process_url(self, url: str) -> None:
        """Process YouTube URL (video or playlist)"""
        logger.info(f"Extracting metadata from: {url}")

        tracks = self.youtube.extract_metadata(url)
        if not tracks:
            logger.error("Could not extract any tracks")
            return

        logger.info(f"Processing {len(tracks)} track(s)")

        success_count = 0
        for i, track in enumerate(tracks, 1):
            logger.info(f"\n[{i}/{len(tracks)}] Processing track...")
            if self.process_track(track):
                success_count += 1

        logger.info(f"\nCompleted: {success_count}/{len(tracks)} tracks successfully processed")


def main():
    parser = argparse.ArgumentParser(
        description='Download music from JioSaavn based on YouTube video/playlist'
    )
    parser.add_argument(
        'url',
        help='YouTube video or playlist URL'
    )
    parser.add_argument(
        '-o', '--output',
        default='downloads',
        help='Output directory (default: downloads)'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    try:
        downloader = MusicDownloader(output_dir=args.output)
        downloader.process_url(args.url)
    except KeyboardInterrupt:
        logger.info("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
