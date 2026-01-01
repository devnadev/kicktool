"""
Downloader Service - Streamlink/yt-dlp/FFmpeg subprocess handling
Supports DVR mode with --hls-live-restart for capturing live streams from beginning
"""

import os
import re
import uuid
import asyncio
import subprocess as sp
from datetime import datetime
from pathlib import Path
from typing import Optional, AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum
import cloudscraper


class DownloadStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"  # FFmpeg remuxing/clipping
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class DownloadProgress:
    """Real-time download progress data"""
    task_id: str
    status: DownloadStatus
    progress: float = 0.0  # 0-100
    speed: str = ""  # e.g., "2.5 MB/s"
    downloaded: str = ""  # e.g., "150.2 MB"
    eta: str = ""  # Estimated time remaining
    message: str = ""
    error: Optional[str] = None


@dataclass
class DownloadRequest:
    """Download request parameters"""
    url: str
    quality: str = "best"
    dvr_mode: bool = False  # Use --hls-live-restart
    start_time: Optional[str] = None  # HH:MM:SS
    end_time: Optional[str] = None  # HH:MM:SS
    output_filename: Optional[str] = None


@dataclass
class DownloadTask:
    """Represents an active download task"""
    task_id: str
    request: DownloadRequest
    status: DownloadStatus = DownloadStatus.PENDING
    progress: float = 0.0
    speed: str = ""
    downloaded: str = ""
    eta: str = ""
    message: str = "Initializing..."
    error: Optional[str] = None
    process: Optional[sp.Popen] = None
    output_path: Optional[str] = None
    temp_path: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    
    @property
    def is_running(self) -> bool:
        return self.status in (DownloadStatus.PENDING, DownloadStatus.DOWNLOADING, DownloadStatus.PROCESSING)
    
    def to_progress(self) -> DownloadProgress:
        return DownloadProgress(
            task_id=self.task_id,
            status=self.status,
            progress=self.progress,
            speed=self.speed,
            downloaded=self.downloaded,
            eta=self.eta,
            message=self.message,
            error=self.error
        )


class DownloaderService:
    """Manages download tasks using Streamlink and FFmpeg"""
    
    def __init__(self, download_dir: str = "./downloads") -> None:
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir = self.download_dir / "temp"
        self.temp_dir.mkdir(exist_ok=True)
        self.tasks: dict[str, DownloadTask] = {}
        self.scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            }
        )
    
    def _get_cookies(self, url: str) -> dict[str, str]:
        """Fetch Cloudflare cookies"""
        try:
            self.scraper.get(url, timeout=15)
            return dict(self.scraper.cookies)
        except Exception:
            return {}
    
    def _sanitize_filename(self, name: str) -> str:
        """Remove invalid characters from filename"""
        return re.sub(r'[<>:"/\\|?*]', '_', name)[:100]
    
    def _parse_time_to_seconds(self, time_str: str) -> int:
        """Convert HH:MM:SS to seconds"""
        parts = time_str.split(':')
        if len(parts) == 3:
            h, m, s = map(int, parts)
            return h * 3600 + m * 60 + s
        elif len(parts) == 2:
            m, s = map(int, parts)
            return m * 60 + s
        return int(parts[0])
    
    async def create_task(self, request: DownloadRequest) -> DownloadTask:
        """Create a new download task"""
        task_id = str(uuid.uuid4())[:8]
        
        # Generate output filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        channel = request.url.split("/")[-1].split("?")[0]
        channel = self._sanitize_filename(channel)
        
        if request.output_filename:
            filename = self._sanitize_filename(request.output_filename)
        else:
            filename = f"{channel}_{timestamp}"
        
        # Final output is always MP4
        output_path = str(self.download_dir / f"{filename}.mp4")
        # Temp is always TS (for Streamlink compatibility)
        temp_path = str(self.temp_dir / f"{task_id}_{filename}.ts")
        
        task = DownloadTask(
            task_id=task_id,
            request=request,
            output_path=output_path,
            temp_path=temp_path
        )
        
        self.tasks[task_id] = task
        return task
    
    async def start_download(self, task_id: str) -> None:
        """Start the download process for a task"""
        import traceback
        task = self.tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        
        try:
            # Get Cloudflare cookies
            task.message = "Bypassing Cloudflare protection..."
            print(f"[DEBUG] Starting download for task {task_id}")
            cookies = await asyncio.to_thread(self._get_cookies, task.request.url)
            print(f"[DEBUG] Got {len(cookies)} cookies")
            
            task.status = DownloadStatus.DOWNLOADING
            task.message = "Starting download..."
            
            # Try Streamlink first (better for Kick.com live streams)
            streamlink_error = None
            try:
                await self._download_with_streamlink(task, cookies)
            except Exception as streamlink_err:
                streamlink_error = str(streamlink_err)
                print(f"[INFO] Streamlink failed: {streamlink_err}")
                print(f"[DEBUG] Streamlink traceback: {traceback.format_exc()}")
                task.message = "Trying alternative method..."
                # Fallback to yt-dlp
                try:
                    await self._download_with_ytdlp(task, cookies)
                except Exception as ytdlp_err:
                    print(f"[ERROR] yt-dlp also failed: {ytdlp_err}")
                    print(f"[DEBUG] yt-dlp traceback: {traceback.format_exc()}")
                    # Combine both errors
                    raise Exception(f"Streamlink: {streamlink_error}; yt-dlp: {str(ytdlp_err)}")
            
            # After download, handle time range clipping and convert to MP4
            await self._process_downloaded_file(task)
            
        except asyncio.CancelledError:
            task.status = DownloadStatus.CANCELLED
            task.message = "Download cancelled"
            self._cleanup_temp(task)
            raise
        except Exception as e:
            error_msg = str(e) if str(e) else "Unknown error occurred"
            print(f"[ERROR] Download failed for task {task_id}: {error_msg}")
            print(f"[DEBUG] Full traceback: {traceback.format_exc()}")
            task.status = DownloadStatus.FAILED
            task.error = error_msg
            task.message = f"Failed: {error_msg}"
            self._cleanup_temp(task)
    
    async def _download_with_streamlink(
        self, 
        task: DownloadTask, 
        cookies: dict[str, str]
    ) -> None:
        """Download using Streamlink (better for Kick.com)"""
        
        # Build command - always output to temp .ts file
        cmd = ["streamlink"]
        
        # Add cookies if available
        if cookies:
            for k, v in cookies.items():
                cmd.append(f"--http-cookie={k}={v}")
        
        # DVR mode - record from the beginning of the stream
        if task.request.dvr_mode:
            cmd.append("--hls-live-restart")
            
            # If start time is specified with DVR, use --hls-start-offset
            if task.request.start_time:
                start_sec = self._parse_time_to_seconds(task.request.start_time)
                cmd.extend(["--hls-start-offset", str(start_sec)])
        
        # If end time specified, calculate duration and use --hls-duration
        if task.request.end_time:
            end_sec = self._parse_time_to_seconds(task.request.end_time)
            start_sec = 0
            if task.request.start_time:
                start_sec = self._parse_time_to_seconds(task.request.start_time)
            duration = end_sec - start_sec
            if duration > 0:
                cmd.extend(["--hls-duration", str(duration)])
        
        # Output path - always use temp .ts file
        cmd.extend(["-o", task.temp_path])
        
        # URL
        cmd.append(task.request.url)
        
        # Quality selection
        if task.request.quality == "best":
            cmd.append("best")
        elif task.request.quality == "audio":
            cmd.append("audio_only")
        else:
            cmd.append(task.request.quality)
        
        # Run download process
        task.message = "Downloading with Streamlink..."
        cmd_str = " ".join(cmd)
        print(f"[DEBUG] Running: {cmd_str}")
        
        # Use subprocess with shell for Windows compatibility
        process = sp.Popen(
            cmd_str,
            shell=True,
            stdout=sp.PIPE,
            stderr=sp.STDOUT,
            text=True,
            bufsize=1
        )
        task.process = process
        
        # Parse output for progress
        file_size = 0
        error_lines = []
        
        try:
            for line_str in iter(process.stdout.readline, ''):
                line_str = line_str.strip()
                if not line_str:
                    continue
                    
                print(f"[STREAMLINK] {line_str}")
                
                # Capture error messages
                if "error:" in line_str.lower() or "Error:" in line_str:
                    error_lines.append(line_str)
                if "No playable streams" in line_str:
                    error_lines.append("No playable streams found - stream may be offline")
                if "Could not open stream" in line_str:
                    error_lines.append(line_str)
                
                # Parse Streamlink progress
                written_match = re.search(r'Written ([\d.]+)\s*(KB|MB|GB)', line_str)
                if written_match:
                    size = float(written_match.group(1))
                    unit = written_match.group(2)
                    if unit == "KB":
                        file_size = size / 1024
                    elif unit == "GB":
                        file_size = size * 1024
                    else:
                        file_size = size
                    task.downloaded = f"{file_size:.1f} MB"
                    task.message = f"Downloading... {task.downloaded}"
                    
                # Track download progress (for live streams, use file size as proxy)
                if file_size > 0:
                    # Estimate progress based on target duration if available
                    if task.request.end_time and task.request.start_time:
                        target_duration = self._parse_time_to_seconds(task.request.end_time) - self._parse_time_to_seconds(task.request.start_time)
                        # Rough estimate: 1 MB per 4 seconds for 1080p
                        estimated_size = target_duration * 0.25  # MB
                        if estimated_size > 0:
                            task.progress = min(99, (file_size / estimated_size) * 100)
        finally:
            process.stdout.close()
            process.wait()
        
        if process.returncode != 0 and process.returncode != 130:  # 130 = interrupted (expected for duration limit)
            error_msg = "; ".join(error_lines) if error_lines else f"Streamlink failed with exit code {process.returncode}"
            raise Exception(error_msg)
        
        # Verify file was created
        if not os.path.exists(task.temp_path):
            raise Exception("Output file was not created")
    
    async def _download_with_ytdlp(
        self, 
        task: DownloadTask, 
        cookies: dict[str, str]
    ) -> None:
        """Download using yt-dlp (fallback)"""
        
        cmd = [
            "yt-dlp",
            "--no-warnings",
            "--newline",
            "--progress-template", "%(progress._percent_str)s|%(progress._speed_str)s|%(progress._downloaded_bytes_str)s|%(progress._eta_str)s",
        ]
        
        # Add cookies
        if cookies:
            cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
            cmd.extend(["--add-header", f"Cookie: {cookie_str}"])
        
        # Quality selection
        if task.request.quality == "best":
            cmd.extend(["-f", "bestvideo+bestaudio/best"])
        elif task.request.quality == "audio":
            cmd.extend(["-f", "bestaudio", "-x", "--audio-format", "mp3"])
        else:
            resolution = task.request.quality.replace("p", "").replace("60", "").replace("30", "")
            cmd.extend(["-f", f"bestvideo[height<={resolution}]+bestaudio/best[height<={resolution}]"])
        
        # DVR mode
        if task.request.dvr_mode:
            cmd.append("--live-from-start")
        
        # Time range - yt-dlp can handle this directly
        if task.request.start_time:
            cmd.extend(["--download-sections", f"*{task.request.start_time}-{task.request.end_time or ''}"])
        
        # Output path - use temp path
        cmd.extend(["-o", task.temp_path])
        cmd.extend(["--merge-output-format", "mp4"])
        
        cmd.append(task.request.url)
        
        task.message = "Downloading with yt-dlp..."
        cmd_str = " ".join(cmd)
        print(f"[DEBUG] Running: {cmd_str}")
        
        process = sp.Popen(
            cmd_str,
            shell=True,
            stdout=sp.PIPE,
            stderr=sp.STDOUT,
            text=True,
            bufsize=1
        )
        task.process = process
        
        try:
            for line_str in iter(process.stdout.readline, ''):
                line_str = line_str.strip()
                if not line_str:
                    continue
                    
                print(f"[YT-DLP] {line_str}")
                self._parse_ytdlp_progress(task, line_str)
        finally:
            process.stdout.close()
            process.wait()
        
        if process.returncode != 0:
            raise Exception("yt-dlp download failed - stream may not be supported")
    
    def _parse_ytdlp_progress(self, task: DownloadTask, line: str) -> None:
        """Parse yt-dlp progress output"""
        if '|' in line and '%' in line:
            try:
                parts = line.split('|')
                if len(parts) >= 4:
                    percent_str = parts[0].strip().replace('%', '').strip()
                    task.progress = float(percent_str) if percent_str != 'N/A' else task.progress
                    task.speed = parts[1].strip() if parts[1].strip() != 'N/A' else ""
                    task.downloaded = parts[2].strip() if parts[2].strip() != 'N/A' else ""
                    task.eta = parts[3].strip() if parts[3].strip() != 'N/A' else ""
            except (ValueError, IndexError):
                pass
        elif "Downloading" in line:
            task.message = "Downloading segments..."
        elif "Merging" in line:
            task.message = "Merging video and audio..."
            task.status = DownloadStatus.PROCESSING
    
    async def _process_downloaded_file(self, task: DownloadTask) -> None:
        """Process the downloaded file - clip if needed and convert to MP4"""
        
        if not os.path.exists(task.temp_path):
            raise Exception("Downloaded file not found")
        
        task.status = DownloadStatus.PROCESSING
        
        # Check if we need to apply time range clipping (post-download)
        # This is for VOD downloads or when Streamlink options weren't used
        needs_post_clip = False
        if not task.request.dvr_mode and (task.request.start_time or task.request.end_time):
            needs_post_clip = True
        
        if needs_post_clip:
            task.message = "Clipping and converting to MP4..."
            await self._clip_and_convert(task)
        else:
            task.message = "Converting to MP4..."
            await self._convert_to_mp4(task)
        
        # Cleanup temp file
        self._cleanup_temp(task)
        
        if os.path.exists(task.output_path):
            task.status = DownloadStatus.COMPLETED
            task.progress = 100.0
            task.message = "Download complete!"
        else:
            raise Exception("Final output file was not created")
    
    async def _clip_and_convert(self, task: DownloadTask) -> None:
        """Clip and convert to MP4 using FFmpeg"""
        
        cmd = ["ffmpeg", "-y"]
        
        # Seek to start time (before input for faster seeking)
        if task.request.start_time:
            cmd.extend(["-ss", task.request.start_time])
        
        cmd.extend(["-i", task.temp_path])
        
        # End time / duration
        if task.request.end_time:
            if task.request.start_time:
                start_sec = self._parse_time_to_seconds(task.request.start_time)
                end_sec = self._parse_time_to_seconds(task.request.end_time)
                duration = end_sec - start_sec
                cmd.extend(["-t", str(duration)])
            else:
                cmd.extend(["-to", task.request.end_time])
        
        # Copy streams and output as MP4
        cmd.extend(["-c", "copy", "-movflags", "+faststart", task.output_path])
        
        cmd_str = " ".join(cmd)
        print(f"[DEBUG] FFmpeg: {cmd_str}")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )
        await process.wait()
        
        if process.returncode != 0:
            raise Exception("Failed to clip and convert video")
    
    async def _convert_to_mp4(self, task: DownloadTask) -> None:
        """Convert TS to MP4 using FFmpeg"""
        
        cmd = [
            "ffmpeg", "-y",
            "-i", task.temp_path,
            "-c", "copy",
            "-movflags", "+faststart",
            task.output_path
        ]
        
        print(f"[DEBUG] FFmpeg: {' '.join(cmd)}")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )
        await process.wait()
        
        if process.returncode != 0:
            raise Exception("Failed to convert to MP4")
    
    def _cleanup_temp(self, task: DownloadTask) -> None:
        """Remove temporary files"""
        if task.temp_path and os.path.exists(task.temp_path):
            try:
                os.remove(task.temp_path)
            except Exception:
                pass
    
    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running download"""
        task = self.tasks.get(task_id)
        if not task:
            return False
        
        if task.process and task.is_running:
            task.process.terminate()
            try:
                task.process.wait(timeout=5)
            except Exception:
                task.process.kill()
        
        task.status = DownloadStatus.CANCELLED
        task.message = "Download cancelled"
        self._cleanup_temp(task)
        return True
    
    def get_task(self, task_id: str) -> Optional[DownloadTask]:
        """Get task by ID"""
        return self.tasks.get(task_id)
    
    async def stream_progress(self, task_id: str) -> AsyncGenerator[DownloadProgress, None]:
        """Async generator for SSE progress updates"""
        task = self.tasks.get(task_id)
        if not task:
            yield DownloadProgress(
                task_id=task_id,
                status=DownloadStatus.FAILED,
                error="Task not found"
            )
            return
        
        last_progress = -1.0
        while task.is_running:
            if task.progress != last_progress or task.status != DownloadStatus.DOWNLOADING:
                yield task.to_progress()
                last_progress = task.progress
            await asyncio.sleep(0.5)
        
        # Final status
        yield task.to_progress()


# Singleton instance
downloader_service = DownloaderService()
