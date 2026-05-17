"""Local video storage for PaperMotion."""

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class LocalStorageBackend:
    """Stores videos on the local filesystem."""

    def __init__(self) -> None:
        self.media_dir = Path(os.getenv("MEDIA_DIR", "./media/videos"))
        self.media_dir.mkdir(parents=True, exist_ok=True)

    async def save_video(self, video_bytes: bytes, filename: str) -> str:
        if not filename.endswith(".mp4"):
            filename = f"{filename}.mp4"

        file_path = self.media_dir / filename
        logger.debug("  [LocalStorage] Writing %s bytes to %s", f"{len(video_bytes):,}", file_path)
        file_path.write_bytes(video_bytes)
        video_id = filename.removesuffix(".mp4")
        return f"/api/video/{video_id}"

    def get_video_path(self, video_id: str) -> Optional[Path]:
        file_path = self.media_dir / f"{video_id}.mp4"
        if file_path.exists():
            return file_path

        file_path = self.media_dir / video_id
        if file_path.exists():
            return file_path

        return None

    def get_video_url(self, video_id: str) -> Optional[str]:
        if self.get_video_path(video_id):
            return f"/api/video/{video_id}"
        return None

    def list_videos(self) -> list[str]:
        return sorted(f.stem for f in self.media_dir.glob("*.mp4"))

    def delete_video(self, video_id: str) -> bool:
        path = self.get_video_path(video_id)
        if path:
            path.unlink()
            return True
        return False


_backend = LocalStorageBackend()


async def save_video(video_bytes: bytes, filename: str) -> str:
    """Save video and return its local API URL."""
    logger.info("  [Storage] Saving video: %s (%s bytes)", filename, f"{len(video_bytes):,}")
    url = await _backend.save_video(video_bytes, filename)
    logger.info("  [Storage] Video saved: %s", url)
    return url


def get_video_path(video_id: str) -> Optional[Path]:
    """Get local file path for a video."""
    return _backend.get_video_path(video_id)


def get_video_url(video_id: str) -> Optional[str]:
    """Get the local API URL for a video if it exists."""
    return _backend.get_video_url(video_id)


def list_videos() -> list[str]:
    """List all video IDs in storage."""
    return _backend.list_videos()


def delete_video(video_id: str) -> bool:
    """Delete a video. Returns True if deleted, False if not found."""
    return _backend.delete_video(video_id)


def get_backend() -> LocalStorageBackend:
    """Get the active backend instance."""
    return _backend
