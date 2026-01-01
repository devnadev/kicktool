"""
Analyzer Service - Kick.com metadata extraction
Uses Kick API directly with cloudscraper fallback to yt-dlp
"""

import json
import re
import asyncio
from typing import Optional
from dataclasses import dataclass, field
import cloudscraper


@dataclass
class StreamFormat:
    """Represents an available stream format/quality"""
    format_id: str
    resolution: str
    fps: Optional[int] = None
    vcodec: str = ""
    acodec: str = ""
    tbr: Optional[float] = None  # Total bitrate
    
    @property
    def label(self) -> str:
        """Human-readable label like '1080p60' or '720p'"""
        if self.fps and self.fps > 30:
            return f"{self.resolution}@{self.fps}fps"
        return self.resolution


@dataclass
class StreamMetadata:
    """Complete stream metadata from analysis"""
    url: str
    title: str
    channel: str
    thumbnail: Optional[str] = None
    duration: Optional[float] = None  # Seconds, None for live
    is_live: bool = False
    formats: list[StreamFormat] = field(default_factory=list)
    playback_url: Optional[str] = None
    error: Optional[str] = None


class AnalyzerService:
    """Analyzes Kick.com URLs using direct API"""
    
    KICK_API_BASE = "https://kick.com/api/v2"
    
    def __init__(self) -> None:
        self.scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            }
        )
    
    def _extract_channel_name(self, url: str) -> Optional[str]:
        """Extract channel/username from Kick URL"""
        # Pattern for https://kick.com/username or https://kick.com/username/...
        match = re.search(r'kick\.com/([a-zA-Z0-9_-]+)', url)
        if match:
            channel = match.group(1)
            # Filter out static paths
            if channel.lower() not in ['video', 'videos', 'clip', 'clips', 'api']:
                return channel
        return None
    
    def _extract_video_id(self, url: str) -> Optional[str]:
        """Extract video ID from VOD URL"""
        # Pattern for https://kick.com/video/uuid
        match = re.search(r'kick\.com/video/([a-zA-Z0-9_-]+)', url)
        if match:
            return match.group(1)
        return None
    
    async def analyze(self, url: str) -> StreamMetadata:
        """
        Analyze a Kick.com URL and extract metadata.
        Uses Kick API directly for better reliability.
        """
        # Validate URL
        if not self._is_valid_kick_url(url):
            return StreamMetadata(
                url=url,
                title="",
                channel="",
                error="Invalid Kick.com URL. Use format: https://kick.com/username"
            )
        
        video_id = self._extract_video_id(url)
        channel_name = self._extract_channel_name(url)
        
        if not channel_name and not video_id:
            return StreamMetadata(
                url=url,
                title="",
                channel="",
                error="Could not extract channel or video from URL"
            )
        
        try:
            if video_id:
                return await self._analyze_vod(url, video_id)
            else:
                return await self._analyze_channel(url, channel_name)
        except Exception as e:
            print(f"[ERROR] Analyze failed: {e}")
            return StreamMetadata(
                url=url,
                title="",
                channel="",
                error=f"Analysis failed: {str(e)}"
            )
    
    async def _analyze_channel(self, url: str, channel_name: str) -> StreamMetadata:
        """Analyze a live channel"""
        try:
            api_url = f"{self.KICK_API_BASE}/channels/{channel_name}"
            response = await asyncio.to_thread(
                self.scraper.get, api_url, timeout=15
            )
            
            if response.status_code == 404:
                return StreamMetadata(
                    url=url,
                    title="",
                    channel=channel_name,
                    error=f"Channel '{channel_name}' not found"
                )
            
            if response.status_code != 200:
                return StreamMetadata(
                    url=url,
                    title="",
                    channel=channel_name,
                    error=f"API error: {response.status_code}"
                )
            
            data = response.json()
            
            # Handle empty or null response
            if data is None:
                return StreamMetadata(
                    url=url,
                    title="",
                    channel=channel_name,
                    error="Empty response from Kick API"
                )
            
            # Check if live - safely handle None
            livestream = data.get("livestream") if isinstance(data, dict) else None
            is_live = False
            if livestream and isinstance(livestream, dict):
                is_live = livestream.get("is_live", False)
            
            if is_live and livestream:
                title = livestream.get("session_title") or f"{channel_name}'s Stream"
                thumb_data = livestream.get("thumbnail")
                thumbnail = thumb_data.get("url") if isinstance(thumb_data, dict) else None
                playback_url = data.get("playback_url")
            else:
                title = f"{channel_name} (Offline)"
                user_data = data.get("user") if isinstance(data, dict) else None
                thumbnail = user_data.get("profile_pic") if isinstance(user_data, dict) else None
                playback_url = None
            
            # Build default format list
            formats = self._get_default_formats()
            
            return StreamMetadata(
                url=url,
                title=title,
                channel=channel_name,
                thumbnail=thumbnail,
                duration=None,
                is_live=is_live,
                formats=formats,
                playback_url=playback_url
            )
            
        except json.JSONDecodeError:
            return StreamMetadata(
                url=url,
                title="",
                channel=channel_name,
                error="Failed to parse Kick API response"
            )
        except Exception as e:
            return StreamMetadata(
                url=url,
                title="",
                channel=channel_name,
                error=f"API request failed: {str(e)}"
            )
    
    async def _analyze_vod(self, url: str, video_id: str) -> StreamMetadata:
        """Analyze a VOD"""
        try:
            api_url = f"{self.KICK_API_BASE}/video/{video_id}"
            response = await asyncio.to_thread(
                self.scraper.get, api_url, timeout=15
            )
            
            if response.status_code == 404:
                return StreamMetadata(
                    url=url,
                    title="",
                    channel="",
                    error="Video not found"
                )
            
            if response.status_code != 200:
                return StreamMetadata(
                    url=url,
                    title="",
                    channel="",
                    error=f"API error: {response.status_code}"
                )
            
            data = response.json()
            
            channel_data = data.get("channel", {})
            channel_name = channel_data.get("slug", "Unknown")
            
            # Calculate duration from start/end times if available
            duration = None
            if data.get("duration"):
                duration = data.get("duration")
            
            formats = self._get_default_formats()
            
            return StreamMetadata(
                url=url,
                title=data.get("title", data.get("session_title", "VOD")),
                channel=channel_name,
                thumbnail=data.get("thumbnail"),
                duration=duration,
                is_live=False,
                formats=formats,
                playback_url=data.get("source")
            )
            
        except json.JSONDecodeError:
            return StreamMetadata(
                url=url,
                title="",
                channel="",
                error="Failed to parse VOD data"
            )
        except Exception as e:
            return StreamMetadata(
                url=url,
                title="",
                channel="",
                error=f"VOD lookup failed: {str(e)}"
            )
    
    def _get_default_formats(self) -> list[StreamFormat]:
        """Return default format options"""
        return [
            StreamFormat(format_id="best", resolution="Best"),
            StreamFormat(format_id="1080p60", resolution="1080p", fps=60),
            StreamFormat(format_id="1080p", resolution="1080p", fps=30),
            StreamFormat(format_id="720p60", resolution="720p", fps=60),
            StreamFormat(format_id="720p", resolution="720p", fps=30),
            StreamFormat(format_id="480p", resolution="480p", fps=30),
            StreamFormat(format_id="360p", resolution="360p", fps=30),
            StreamFormat(format_id="audio", resolution="Audio Only"),
        ]
    
    def _is_valid_kick_url(self, url: str) -> bool:
        """Validate that URL is a valid Kick.com URL"""
        pattern = r'^https?://(www\.)?kick\.com/[\w\-]+'
        return bool(re.match(pattern, url, re.IGNORECASE))


# Singleton instance
analyzer_service = AnalyzerService()


async def analyze_url(url: str) -> StreamMetadata:
    """Convenience function to analyze a URL"""
    return await analyzer_service.analyze(url)
