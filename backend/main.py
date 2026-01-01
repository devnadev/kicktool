"""
Kick.com DVR & VOD Downloader - v5 (FINAL FIX)

KEY INSIGHT from kick-video.download:
They get the m3u8 playback_url DIRECTLY from Kick's API and download HLS segments
with timestamp-based seeking using FFmpeg, NOT Streamlink's --hls-live-restart.

The correct approach:
1. Get playback_url from /api/v2/channels/{channel}/livestream
2. Use FFmpeg to download directly from m3u8 with timestamp seeking
"""

import os
import re
import json
import uuid
import asyncio
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
import cloudscraper
import m3u8
import tempfile


# ============================================================================
# Configuration
# ============================================================================

DOWNLOAD_DIR = Path("./downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)
TEMP_DIR = DOWNLOAD_DIR / "temp"
TEMP_DIR.mkdir(exist_ok=True)


# ============================================================================
# Pydantic Models
# ============================================================================

class AnalyzeRequest(BaseModel):
    url: str


class AnalyzeResponse(BaseModel):
    success: bool
    url: str
    title: str = ""
    channel: str = ""
    thumbnail: Optional[str] = None
    duration: Optional[float] = None
    is_live: bool = False
    is_vod: bool = False
    playback_url: Optional[str] = None
    formats: list = []
    error: Optional[str] = None


class DownloadRequest(BaseModel):
    url: str
    quality: str = "best"
    dvr_mode: bool = False
    start_time: Optional[str] = None
    end_time: Optional[str] = None


class DownloadResponse(BaseModel):
    success: bool
    task_id: str
    message: str
    error: Optional[str] = None


# ============================================================================
# Global State
# ============================================================================

tasks = {}
scraper = cloudscraper.create_scraper()


def time_to_seconds(time_str: str) -> int:
    """Convert HH:MM:SS or MM:SS to seconds"""
    if not time_str:
        return 0
    parts = time_str.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        else:
            return int(parts[0])
    except:
        return 0


def get_playback_url(channel_name: str) -> Optional[str]:
    """
    Get the m3u8 playback URL directly from Kick's API.
    This is the KEY to how kick-video.download works!
    """
    try:
        # First get channel info with livestream data
        api_url = f"https://kick.com/api/v2/channels/{channel_name}"
        response = scraper.get(api_url, timeout=15)
        
        if response.status_code != 200:
            print(f"[API] Channel not found: {response.status_code}")
            return None
        
        data = response.json()
        
        # Check if live
        livestream = data.get("livestream")
        if not livestream:
            print("[API] Channel is not live")
            return None
        
        # The playback_url is in the livestream object
        playback_url = data.get("playback_url")
        
        if playback_url:
            # Remove escape characters if present
            playback_url = playback_url.replace("\\", "")
            print(f"[API] Got playback URL: {playback_url[:80]}...")
            return playback_url
        
        # Alternative: try the video object in livestream
        if isinstance(livestream, dict):
            source = livestream.get("source")
            if source:
                print(f"[API] Got source URL: {source[:80]}...")
                return source
        
        print("[API] No playback URL found in response")
        return None
        
    except Exception as e:
        print(f"[API] Error getting playback URL: {e}")
        return None


def get_vod_playback_url(video_id: str) -> Optional[str]:
    """Get m3u8 URL for a VOD"""
    try:
        api_url = f"https://kick.com/api/v2/video/{video_id}"
        response = scraper.get(api_url, timeout=15)
        
        if response.status_code != 200:
            return None
        
        data = response.json()
        source = data.get("source")
        
        if source:
            source = source.replace("\\", "")
            print(f"[API] Got VOD source: {source[:80]}...")
            return source
        
        return None
    except Exception as e:
        print(f"[API] Error getting VOD URL: {e}")
        return None


def create_task(url: str, quality: str, dvr_mode: bool, start_time: str, end_time: str, playback_url: str = None) -> dict:
    """Create a new download task"""
    task_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Extract identifier from URL
    if "/video/" in url:
        identifier = f"vod_{url.split('/video/')[-1].split('?')[0]}"
    else:
        identifier = url.split("/")[-1].split("?")[0]
    
    identifier = re.sub(r'[<>:"/\\|?*]', '_', identifier)[:50]
    filename = f"{identifier}_{timestamp}.mp4"
    
    task = {
        "task_id": task_id,
        "url": url,
        "playback_url": playback_url,
        "quality": quality,
        "dvr_mode": dvr_mode,
        "start_time": start_time,
        "end_time": end_time,
        "output_path": str(DOWNLOAD_DIR / filename),
        "temp_path": str(TEMP_DIR / f"{task_id}_{identifier}.ts"),
        "status": "pending",
        "progress": 0.0,
        "message": "Initializing...",
        "error": None,
        "speed": "",
        "downloaded": "",
        "eta": ""
    }
    
    tasks[task_id] = task
    print(f"[TASK] Created: {task_id}")
    return task


async def run_download(task_id: str):
    """
    Run the download process.
    
    KEY DIFFERENCE from before:
    We now use FFmpeg to download DIRECTLY from the m3u8 URL with -ss and -t flags
    for precise timestamp-based clipping. This is how kick-video.download works!
    """
    task = tasks.get(task_id)
    if not task:
        return
    
    print(f"\n{'='*60}")
    print(f"[DOWNLOAD] Task {task_id}")
    print(f"[DOWNLOAD] URL: {task['url']}")
    print(f"[DOWNLOAD] Playback URL: {task['playback_url'][:80] if task['playback_url'] else 'None'}...")
    print(f"[DOWNLOAD] Time Range: {task['start_time']} -> {task['end_time']}")
    print(f"{'='*60}\n")
    
    try:
        task["status"] = "downloading"
        
        if task["playback_url"]:
            # Check if this is a live stream DVR request with time range
            # For live streams with time range, use segment-based download
            # because FFmpeg -ss seeks from live edge, not stream start
            is_vod = "/video/" in task["url"]
            has_time_range = task["start_time"] or task["end_time"]
            
            if not is_vod and has_time_range and task["dvr_mode"]:
                # LIVE STREAM with time range - use segment-based download
                print("[DOWNLOAD] Live stream with time range - using segment-based download")
                await download_with_hls_segments(task)
            else:
                # VOD or live stream without time range - use direct FFmpeg
                await download_with_ffmpeg_direct(task)
        else:
            # Fallback to Streamlink
            await download_with_streamlink(task)
        
    except Exception as e:
        error_msg = str(e) if str(e) else "Unknown error"
        print(f"\n[ERROR] Task {task_id} failed: {error_msg}")
        task["status"] = "failed"
        task["error"] = error_msg
        task["message"] = f"Failed: {error_msg}"
        
        try:
            if os.path.exists(task["temp_path"]):
                os.remove(task["temp_path"])
        except:
            pass


async def download_with_ffmpeg_direct(task: dict):
    """
    Download directly from m3u8 using FFmpeg with timestamp-based seeking.
    
    THIS IS THE KEY DIFFERENCE!
    FFmpeg can seek in HLS streams using -ss (start time) and -t (duration).
    This allows clipping from ANY point in the stream's DVR buffer!
    """
    
    m3u8_url = task["playback_url"]
    
    # Build FFmpeg command
    cmd = ["ffmpeg", "-y"]
    
    # Add headers for Cloudflare
    cmd.extend([
        "-headers", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36\\r\\n"
    ])
    
    # TIME SEEKING - This is the magic!
    # -ss BEFORE -i means seek to this point in the stream
    if task["start_time"]:
        cmd.extend(["-ss", task["start_time"]])
        task["message"] = f"Seeking to {task['start_time']}..."
        print(f"[FFMPEG] Seeking to start time: {task['start_time']}")
    
    # Input m3u8 URL
    cmd.extend(["-i", m3u8_url])
    
    # Duration limit
    if task["end_time"]:
        start_sec = time_to_seconds(task["start_time"]) if task["start_time"] else 0
        end_sec = time_to_seconds(task["end_time"])
        duration = end_sec - start_sec
        if duration > 0:
            cmd.extend(["-t", str(duration)])
            print(f"[FFMPEG] Duration: {duration} seconds")
    
    # Output options
    cmd.extend([
        "-c", "copy",  # Copy streams without re-encoding (fast!)
        "-bsf:a", "aac_adtstoasc",  # Fix audio for MP4 container
        "-movflags", "+faststart",  # Enable web playback
        task["output_path"]
    ])
    
    cmd_str = " ".join(cmd)
    print(f"[CMD] {cmd_str}")
    
    task["message"] = "Downloading from stream..."
    
    # Run FFmpeg
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    
    duration_sec = 0
    for line in iter(process.stdout.readline, ''):
        line = line.strip()
        if not line:
            continue
        
        # Don't spam logs
        if "frame=" in line or "time=" in line:
            # Parse time progress
            match = re.search(r'time=(\d+):(\d+):(\d+)', line)
            if match:
                h, m, s = int(match.group(1)), int(match.group(2)), int(match.group(3))
                current = h * 3600 + m * 60 + s
                task["downloaded"] = f"{current}s"
                task["message"] = f"Downloading... {current}s captured"
        elif "error" in line.lower():
            print(f"[FFMPEG] {line}")
    
    process.wait()
    
    if process.returncode != 0:
        raise Exception("FFmpeg download failed")
    
    # Verify output
    if not os.path.exists(task["output_path"]):
        raise Exception("Output file was not created")
    
    output_size = os.path.getsize(task["output_path"]) / (1024 * 1024)
    
    task["status"] = "completed"
    task["progress"] = 100.0
    task["message"] = f"✅ Download complete! ({output_size:.1f} MB)"
    
    print(f"\n[SUCCESS] {task['output_path']} ({output_size:.1f} MB)")


async def download_with_hls_segments(task: dict):
    """
    Download live stream segments based on time range from STREAM START.
    
    This solves the problem where FFmpeg's -ss flag seeks from the live edge
    instead of the stream beginning. We:
    1. Parse the m3u8 playlist to get all available segments
    2. Calculate cumulative time from the first segment (stream start)
    3. Identify which segments fall within our requested time range
    4. Download only those specific segments
    5. Concatenate them with FFmpeg
    """
    
    m3u8_url = task["playback_url"]
    task["message"] = "Parsing HLS playlist..."
    print(f"[HLS] Loading playlist: {m3u8_url[:80]}...")
    
    # Load the m3u8 playlist
    try:
        playlist = m3u8.load(m3u8_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
    except Exception as e:
        print(f"[HLS] Failed to load playlist: {e}")
        raise Exception(f"Failed to load HLS playlist: {e}")
    
    # Handle master playlist - get highest quality variant
    if playlist.is_variant:
        print(f"[HLS] Master playlist detected, {len(playlist.playlists)} variants available")
        # Sort by bandwidth and get the best one
        variants = sorted(playlist.playlists, key=lambda p: p.stream_info.bandwidth or 0, reverse=True)
        best_variant = variants[0]
        print(f"[HLS] Selected best quality: {best_variant.stream_info.bandwidth} bps")
        
        # Load the actual media playlist
        playlist = m3u8.load(best_variant.absolute_uri, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
    
    if not playlist.segments:
        raise Exception("No segments found in HLS playlist")
    
    print(f"[HLS] Found {len(playlist.segments)} segments in playlist")
    
    # Calculate segment times from stream start (segment 0 = time 0)
    segments_with_times = []
    current_time = 0.0
    
    for i, seg in enumerate(playlist.segments):
        seg_info = {
            "index": i,
            "uri": seg.absolute_uri if seg.absolute_uri else seg.uri,
            "start": current_time,
            "end": current_time + seg.duration,
            "duration": seg.duration
        }
        segments_with_times.append(seg_info)
        current_time += seg.duration
    
    total_duration = current_time
    print(f"[HLS] Total DVR duration: {total_duration:.1f} seconds ({total_duration/60:.1f} minutes)")
    
    # Determine requested time range
    start_sec = time_to_seconds(task["start_time"]) if task["start_time"] else 0
    end_sec = time_to_seconds(task["end_time"]) if task["end_time"] else total_duration
    
    print(f"[HLS] Requested time range: {start_sec}s - {end_sec}s")
    
    # Find segments that overlap with our requested time range
    selected_segments = []
    for seg in segments_with_times:
        # Segment overlaps if it ends after our start AND starts before our end
        if seg["end"] > start_sec and seg["start"] < end_sec:
            selected_segments.append(seg)
    
    if not selected_segments:
        raise Exception(f"No segments found in requested time range ({start_sec}s - {end_sec}s). Total DVR duration: {total_duration:.1f}s")
    
    print(f"[HLS] Selected {len(selected_segments)} segments (indices {selected_segments[0]['index']} to {selected_segments[-1]['index']})")
    
    # Create temp directory for segments
    temp_dir = Path(tempfile.mkdtemp(prefix="hls_segments_"))
    segment_files = []
    
    try:
        task["message"] = f"Downloading {len(selected_segments)} segments..."
        
        # Download each segment
        for i, seg in enumerate(selected_segments):
            progress = (i + 1) / len(selected_segments) * 80  # 80% for download
            task["progress"] = progress
            task["message"] = f"Downloading segment {i+1}/{len(selected_segments)}..."
            
            segment_path = temp_dir / f"segment_{i:05d}.ts"
            
            try:
                response = scraper.get(seg["uri"], timeout=30, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                response.raise_for_status()
                
                with open(segment_path, "wb") as f:
                    f.write(response.content)
                
                segment_files.append(str(segment_path))
                
            except Exception as e:
                print(f"[HLS] Failed to download segment {i}: {e}")
                raise Exception(f"Failed to download segment {i}: {e}")
        
        print(f"[HLS] Downloaded {len(segment_files)} segments to {temp_dir}")
        
        # Create FFmpeg concat file
        concat_file = temp_dir / "concat.txt"
        with open(concat_file, "w") as f:
            for seg_path in segment_files:
                # FFmpeg concat requires forward slashes and proper escaping
                escaped_path = seg_path.replace("\\", "/")
                f.write(f"file '{escaped_path}'\n")
        
        task["message"] = "Joining segments..."
        task["progress"] = 85
        
        # Use FFmpeg to concatenate and trim to exact time range
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file)]
        
        # Calculate trim points within the concatenated segments
        # The first selected segment starts at selected_segments[0]["start"]
        # We need to trim the beginning to get to our exact start time
        first_seg_start = selected_segments[0]["start"]
        trim_start = start_sec - first_seg_start
        
        if trim_start > 0:
            cmd.extend(["-ss", str(trim_start)])
        
        # Calculate duration
        requested_duration = end_sec - start_sec
        cmd.extend(["-t", str(requested_duration)])
        
        # Output options
        cmd.extend([
            "-c", "copy",
            "-bsf:a", "aac_adtstoasc",
            "-movflags", "+faststart",
            task["output_path"]
        ])
        
        print(f"[CMD] {' '.join(cmd)}")
        
        task["message"] = "Converting to MP4..."
        task["progress"] = 90
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        for line in iter(process.stdout.readline, ''):
            line = line.strip()
            if line and ("error" in line.lower() or "warning" in line.lower()):
                print(f"[FFMPEG] {line}")
        
        process.wait()
        
        if process.returncode != 0:
            raise Exception("FFmpeg concatenation failed")
        
        # Verify output
        if not os.path.exists(task["output_path"]):
            raise Exception("Output file was not created")
        
        output_size = os.path.getsize(task["output_path"]) / (1024 * 1024)
        
        task["status"] = "completed"
        task["progress"] = 100.0
        task["message"] = f"✅ Download complete! ({output_size:.1f} MB)"
        
        print(f"\n[SUCCESS] {task['output_path']} ({output_size:.1f} MB)")
        print(f"[SUCCESS] Downloaded time range: {start_sec}s - {end_sec}s from STREAM START")
        
    finally:
        # Cleanup temp directory
        try:
            import shutil
            shutil.rmtree(temp_dir)
            print(f"[HLS] Cleaned up temp directory: {temp_dir}")
        except Exception as e:
            print(f"[HLS] Failed to cleanup temp directory: {e}")


async def download_with_streamlink(task: dict):
    """Fallback: Download using Streamlink when we don't have a playback URL"""
    
    task["message"] = "Downloading with Streamlink..."
    
    cmd = ["streamlink"]
    
    # Get cookies
    try:
        scraper.get(task["url"], timeout=10)
        for k, v in scraper.cookies.items():
            cmd.append(f"--http-cookie={k}={v}")
    except:
        pass
    
    # Duration limit
    if task["end_time"]:
        start_sec = time_to_seconds(task["start_time"]) if task["start_time"] else 0
        end_sec = time_to_seconds(task["end_time"])
        duration = end_sec - start_sec
        if duration > 0:
            cmd.extend(["--hls-duration", str(duration)])
    
    cmd.extend(["-o", task["temp_path"]])
    cmd.append(task["url"])
    cmd.append(task["quality"] if task["quality"] else "best")
    
    print(f"[CMD] {' '.join(cmd)}")
    
    process = subprocess.Popen(
        " ".join(cmd),
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    
    for line in iter(process.stdout.readline, ''):
        line = line.strip()
        if not line:
            continue
        print(f"[STREAM] {line}")
        
        match = re.search(r'Written ([\d.]+)\s*(KB|MB|GB)', line)
        if match:
            size = float(match.group(1))
            unit = match.group(2)
            if unit == "KB":
                size = size / 1024
            elif unit == "GB":
                size = size * 1024
            task["downloaded"] = f"{size:.1f} MB"
            task["message"] = f"Recording... {size:.1f} MB"
    
    process.wait()
    
    if process.returncode not in [0, 130]:
        raise Exception("Streamlink failed")
    
    # Convert to MP4
    if os.path.exists(task["temp_path"]):
        task["message"] = "Converting to MP4..."
        
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", task["temp_path"],
            "-c", "copy",
            "-movflags", "+faststart",
            task["output_path"]
        ]
        
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise Exception("FFmpeg conversion failed")
        
        os.remove(task["temp_path"])
    
    if not os.path.exists(task["output_path"]):
        raise Exception("Output file was not created")
    
    output_size = os.path.getsize(task["output_path"]) / (1024 * 1024)
    
    task["status"] = "completed"
    task["progress"] = 100.0
    task["message"] = f"✅ Download complete! ({output_size:.1f} MB)"
    
    print(f"\n[SUCCESS] {task['output_path']} ({output_size:.1f} MB)")


# ============================================================================
# App Lifecycle
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("\n" + "="*70)
    print("🚀 Kick.com DVR & VOD Downloader v5 (FINAL FIX)")
    print("="*70)
    print("\n✨ NEW: Direct m3u8 download with FFmpeg timestamp seeking!")
    print("   This matches how kick-video.download works.")
    print("   Time range clipping should now work for live streams!")
    print("="*70 + "\n")
    yield
    print("👋 Shutting down...")


# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="Kick.com DVR & VOD Downloader",
    version="5.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Routes
# ============================================================================

@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "Kick.com DVR & VOD Downloader v5",
        "feature": "Direct m3u8 download with timestamp seeking"
    }


@app.post("/api/analyze")
async def analyze_stream(request: AnalyzeRequest):
    """Analyze a Kick.com URL and get the playback URL"""
    print(f"[API] Analyzing: {request.url}")
    
    try:
        is_vod = "/video/" in request.url
        
        if not re.match(r'^https?://(www\.)?kick\.com/', request.url, re.IGNORECASE):
            return AnalyzeResponse(
                success=False,
                url=request.url,
                error="Invalid Kick.com URL"
            )
        
        if is_vod:
            video_id = request.url.split("/video/")[-1].split("?")[0]
            playback_url = get_vod_playback_url(video_id)
            
            # Get VOD info
            try:
                api_url = f"https://kick.com/api/v2/video/{video_id}"
                response = scraper.get(api_url, timeout=15)
                if response.status_code == 200:
                    data = response.json()
                    return AnalyzeResponse(
                        success=True,
                        url=request.url,
                        title=data.get("session_title", f"VOD {video_id}"),
                        channel=data.get("channel", {}).get("slug", "unknown"),
                        thumbnail=data.get("thumbnail"),
                        duration=data.get("duration"),
                        is_live=False,
                        is_vod=True,
                        playback_url=playback_url,
                        formats=[
                            {"format_id": "best", "resolution": "Best", "label": "Best Quality"},
                            {"format_id": "source", "resolution": "Source", "label": "Source"},
                        ]
                    )
            except:
                pass
            
            return AnalyzeResponse(
                success=True,
                url=request.url,
                title=f"VOD {video_id}",
                is_vod=True,
                playback_url=playback_url,
                formats=[{"format_id": "best", "resolution": "Best", "label": "Best Quality"}]
            )
        else:
            channel_name = request.url.split("/")[-1].split("?")[0]
            playback_url = get_playback_url(channel_name)
            
            # Get channel info
            try:
                api_url = f"https://kick.com/api/v2/channels/{channel_name}"
                response = scraper.get(api_url, timeout=15)
                if response.status_code == 200:
                    data = response.json()
                    
                    livestream = data.get("livestream")
                    is_live = livestream is not None
                    
                    if is_live and isinstance(livestream, dict):
                        title = livestream.get("session_title", f"{channel_name}'s Stream")
                        thumb = livestream.get("thumbnail", {})
                        thumbnail = thumb.get("url") if isinstance(thumb, dict) else None
                    else:
                        title = f"{channel_name} (Offline)"
                        thumbnail = None
                    
                    return AnalyzeResponse(
                        success=True,
                        url=request.url,
                        title=title,
                        channel=channel_name,
                        thumbnail=thumbnail,
                        is_live=is_live,
                        is_vod=False,
                        playback_url=playback_url,
                        formats=[
                            {"format_id": "best", "resolution": "Best", "label": "Best Quality"},
                            {"format_id": "1080p60", "resolution": "1080p", "label": "1080p60"},
                            {"format_id": "720p60", "resolution": "720p", "label": "720p60"},
                        ]
                    )
            except Exception as e:
                print(f"[ERROR] {e}")
            
            return AnalyzeResponse(
                success=True,
                url=request.url,
                title=channel_name,
                channel=channel_name,
                is_live=True,
                playback_url=playback_url,
                formats=[{"format_id": "best", "resolution": "Best", "label": "Best Quality"}]
            )
            
    except Exception as e:
        return AnalyzeResponse(
            success=False,
            url=request.url,
            error=str(e)
        )


@app.post("/api/download")
async def start_download(request: DownloadRequest, background_tasks: BackgroundTasks):
    """Start a new download"""
    print(f"\n[API] Download request:")
    print(f"      URL: {request.url}")
    print(f"      Range: {request.start_time} -> {request.end_time}")
    
    try:
        # Get playback URL first!
        playback_url = None
        if "/video/" in request.url:
            video_id = request.url.split("/video/")[-1].split("?")[0]
            playback_url = get_vod_playback_url(video_id)
        else:
            channel_name = request.url.split("/")[-1].split("?")[0]
            playback_url = get_playback_url(channel_name)
        
        if playback_url:
            print(f"[API] Got playback URL!")
        else:
            print(f"[API] No playback URL, will use Streamlink fallback")
        
        task = create_task(
            url=request.url,
            quality=request.quality,
            dvr_mode=request.dvr_mode,
            start_time=request.start_time,
            end_time=request.end_time,
            playback_url=playback_url
        )
        
        background_tasks.add_task(run_download, task["task_id"])
        
        return DownloadResponse(
            success=True,
            task_id=task["task_id"],
            message=f"Download started: {task['task_id']}"
        )
        
    except Exception as e:
        print(f"[ERROR] {e}")
        return DownloadResponse(
            success=False,
            task_id="",
            message="",
            error=str(e)
        )


@app.get("/api/events/{task_id}")
async def stream_events(task_id: str):
    """SSE endpoint for download progress"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    async def event_generator():
        while True:
            task = tasks.get(task_id, {})
            
            data = {
                "task_id": task_id,
                "status": task.get("status", "unknown"),
                "progress": task.get("progress", 0),
                "message": task.get("message", ""),
                "error": task.get("error", ""),
                "speed": task.get("speed", ""),
                "downloaded": task.get("downloaded", ""),
                "eta": task.get("eta", "")
            }
            
            yield {"event": "progress", "data": json.dumps(data)}
            
            if task.get("status") in ["completed", "failed", "cancelled"]:
                break
            
            await asyncio.sleep(0.5)
    
    return EventSourceResponse(event_generator())


@app.get("/api/downloads/{task_id}")
async def get_task_status(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks[task_id]


@app.get("/api/downloads")
async def list_downloads():
    return {"tasks": list(tasks.values())}


# ============================================================================
# Run
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
