"""Batch manager for Facebook Group URLs and execution state.

Uses generators to stream URLs lazily and avoid loading large files in memory.
Tracks execution history to allow resumable operations.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, List, Dict, Any, Optional


class GroupBatchManager:
    """Manages loading group URLs in batches and tracking post history."""

    def __init__(self, groups_file: Path, history_file: Path, batch_size: int = 10) -> None:
        self.groups_file = groups_file
        self.history_file = history_file
        self.batch_size = max(1, batch_size)
        self.history: Dict[str, Dict[str, Any]] = self._load_history()

    def _load_history(self) -> Dict[str, Dict[str, Any]]:
        """Load past execution history from JSON file."""
        if not self.history_file.exists():
            return {}
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_history(self) -> None:
        """Persist post history to JSON file atomically."""
        temp_file = self.history_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(self.history, f, indent=2, ensure_ascii=False)
        temp_file.replace(self.history_file)

    def is_processed(self, group_url: str) -> bool:
        """Check if group URL was already successfully posted to."""
        entry = self.history.get(group_url.strip())
        if not entry:
            return False
        return entry.get("status") in ("SUCCESS", "PENDING_APPROVAL")

    def record_result(
        self,
        group_url: str,
        status: str,
        details: Optional[str] = None,
    ) -> None:
        """Record post result for a group URL."""
        cleaned_url = group_url.strip()
        self.history[cleaned_url] = {
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details or "",
        }
        self._save_history()

    def stream_pending_groups(self, ignore_history: bool = False) -> Generator[str, None, None]:
        """Stream unprocessed group URLs line by line using a generator."""
        if not self.groups_file.exists():
            raise FileNotFoundError(f"Groups file not found at: {self.groups_file}")

        with open(self.groups_file, "r", encoding="utf-8") as f:
            for line in f:
                cleaned = line.strip()
                if not cleaned or cleaned.startswith("#"):
                    continue
                if ignore_history or not self.is_processed(cleaned):
                    yield cleaned

    def stream_batches(self, ignore_history: bool = False) -> Generator[List[str], None, None]:
        """Yield batches of pending group URLs using a generator."""
        current_batch: List[str] = []
        for group_url in self.stream_pending_groups(ignore_history=ignore_history):
            current_batch.append(group_url)
            if len(current_batch) >= self.batch_size:
                yield current_batch
                current_batch = []

        if current_batch:
            yield current_batch

    def get_stats(self) -> Dict[str, int]:
        """Return counts of processed and total groups."""
        successful = sum(
            1 for item in self.history.values() if item.get("status") in ("SUCCESS", "PENDING_APPROVAL")
        )
        failed = sum(
            1 for item in self.history.values() if item.get("status") == "FAILED"
        )
        skipped = sum(
            1 for item in self.history.values() if item.get("status") in ("NOT_A_MEMBER", "BLOCKED")
        )
        return {
            "successful": successful,
            "failed": failed,
            "skipped": skipped,
            "total_recorded": len(self.history),
        }
