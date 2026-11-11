"""Batch manager for Facebook Group URLs and execution state backed by SQLite.

Uses generators to stream URLs lazily and avoid loading large files or tables in memory.
Tracks execution history and captured post URLs per campaign in embedded SQLite.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from storage.database import DatabaseManager
from storage.repositories import (
    CampaignRepository,
    GroupRepository,
    LegacyMigrator,
    PostRepository,
    stream_urls_from_file,
)


class GroupBatchManager:
    """Manages loading group URLs in batches and tracking campaign post history in SQLite."""

    def __init__(
        self,
        groups_file: Optional[Path] = None,
        history_file: Optional[Path] = None,
        batch_size: int = 10,
        db: Optional[DatabaseManager] = None,
        db_path: Optional[Path] = None,
        campaign_id: Optional[int] = None,
    ) -> None:
        self.groups_file = groups_file
        self.history_file = history_file
        self.batch_size = max(1, batch_size)

        if db is not None:
            self.db = db
            self._owns_db = False
        else:
            resolved_db_path = db_path or (
                history_file.with_suffix(".db") if history_file else Path("fb_manager.db")
            )
            self.db = DatabaseManager(resolved_db_path)
            self._owns_db = True

        self.group_repo = GroupRepository(self.db)
        self.campaign_repo = CampaignRepository(self.db)
        self.post_repo = PostRepository(self.db)

        LegacyMigrator.migrate_if_needed(
            self.db,
            groups_file=self.groups_file,
            history_file=self.history_file,
        )
        if self.groups_file and self.groups_file.exists():
            self.group_repo.import_from_txt(self.groups_file)

        if campaign_id is not None:
            self.campaign_id = campaign_id
        else:
            active = self.campaign_repo.get_active_campaign()
            if active is not None:
                self.campaign_id = active.id
            else:
                default_campaign = self.campaign_repo.create_campaign(
                    name="Default Campaign",
                    post_text="",
                    bundle_dir=None,
                    content_hash="default",
                    activate=True,
                )
                self.campaign_id = default_campaign.id

    @property
    def history(self) -> Dict[str, Dict[str, Any]]:
        """Return a snapshot dictionary of group statuses for the active campaign."""
        status_map = self.post_repo.get_status_map(self.campaign_id)
        return {
            url: {
                "status": rec.status,
                "timestamp": rec.updated_at,
                "details": rec.details,
                "post_url": rec.post_url,
                "fb_post_id": rec.fb_post_id,
            }
            for url, rec in status_map.items()
        }

    def is_processed(self, group_url: str) -> bool:
        """Check if group URL was already successfully posted to in the current campaign."""
        return self.post_repo.is_group_processed(self.campaign_id, group_url)

    def record_result(
        self,
        group_url: str,
        status: str,
        details: Optional[str] = None,
        post_url: Optional[str] = None,
        fb_post_id: Optional[str] = None,
    ) -> None:
        """Persist post result and optional captured post URL to SQLite."""
        self.post_repo.record_post(
            campaign_id=self.campaign_id,
            group_url=group_url,
            status=status,
            details=details or "",
            post_url=post_url,
            fb_post_id=fb_post_id,
        )

    def stream_pending_groups(
        self, ignore_history: bool = False
    ) -> Generator[str, None, None]:
        """Stream unprocessed group URLs lazily using a generator."""
        if self.groups_file is not None:
            url_source = stream_urls_from_file(self.groups_file)
        else:
            url_source = (
                group.url for group in self.group_repo.stream_groups(status="ACTIVE")
            )

        for cleaned in url_source:
            if ignore_history or not self.is_processed(cleaned):
                yield cleaned

    def stream_batches(
        self, ignore_history: bool = False
    ) -> Generator[List[str], None, None]:
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
        """Return aggregated execution counts for the current campaign."""
        return self.post_repo.get_campaign_stats(self.campaign_id)

    def close(self) -> None:
        """Close the underlying database manager if owned by this batch manager."""
        if self._owns_db:
            self.db.close()
