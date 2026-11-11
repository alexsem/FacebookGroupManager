"""OOP repositories and legacy migration helpers backed by SQLite."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Dict, Generator, Iterable, List, Optional, Sequence

from storage.database import DatabaseManager, utc_now_iso
from storage.models import (
    CampaignRecord,
    CampaignSummary,
    GroupRecord,
    PostRecord,
    compute_content_hash,
)

PROCESSED_STATUSES = ("SUCCESS", "PENDING_APPROVAL")


def _row_to_group(row: sqlite3.Row) -> GroupRecord:
    return GroupRecord(
        id=row["id"],
        url=row["url"],
        name=row["name"],
        status=row["status"],
        notes=row["notes"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_campaign(row: sqlite3.Row) -> CampaignRecord:
    return CampaignRecord(
        id=row["id"],
        name=row["name"],
        bundle_dir=row["bundle_dir"],
        post_text=row["post_text"],
        content_hash=row["content_hash"],
        is_active=bool(row["is_active"]),
        created_at=row["created_at"],
    )


def _row_to_post(row: sqlite3.Row) -> PostRecord:
    keys = row.keys()
    return PostRecord(
        id=row["id"],
        campaign_id=row["campaign_id"],
        group_id=row["group_id"],
        group_url=row["group_url"],
        status=row["status"],
        post_url=row["post_url"],
        fb_post_id=row["fb_post_id"],
        details=row["details"],
        published_at=row["published_at"],
        updated_at=row["updated_at"],
        campaign_name=row["campaign_name"] if "campaign_name" in keys else None,
    )


def stream_urls_from_file(file_path: Path) -> Generator[str, None, None]:
    """Yield cleaned group URLs line-by-line from a text file without loading it in memory."""
    if not file_path.exists():
        raise FileNotFoundError(f"Groups file not found at: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            cleaned = line.strip()
            if cleaned and not cleaned.startswith("#"):
                yield cleaned


class GroupRepository:
    """Manages persistence of Facebook groups."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def upsert_group(
        self,
        url: str,
        name: Optional[str] = None,
        status: str = "ACTIVE",
        notes: Optional[str] = None,
    ) -> GroupRecord:
        """Insert a group or update its metadata if it already exists."""
        cleaned_url = url.strip()
        now = utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO groups (url, name, status, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    name = COALESCE(excluded.name, groups.name),
                    status = COALESCE(excluded.status, groups.status),
                    notes = COALESCE(excluded.notes, groups.notes),
                    updated_at = excluded.updated_at
                """,
                (cleaned_url, name, status, notes, now, now),
            )
            row = conn.execute(
                "SELECT * FROM groups WHERE url = ?", (cleaned_url,)
            ).fetchone()
            assert row is not None
            return _row_to_group(row)

    def ensure_group(self, conn: sqlite3.Connection, url: str) -> int:
        """Ensure a group row exists inside an active transaction and return its id."""
        cleaned_url = url.strip()
        row = conn.execute(
            "SELECT id FROM groups WHERE url = ?", (cleaned_url,)
        ).fetchone()
        if row is not None:
            return int(row["id"])
        now = utc_now_iso()
        cur = conn.execute(
            """
            INSERT INTO groups (url, status, created_at, updated_at)
            VALUES (?, 'ACTIVE', ?, ?)
            """,
            (cleaned_url, now, now),
        )
        assert cur.lastrowid is not None
        return int(cur.lastrowid)

    def get_by_url(self, url: str) -> Optional[GroupRecord]:
        cleaned_url = url.strip()
        with self.db.read_cursor() as cur:
            row = cur.execute(
                "SELECT * FROM groups WHERE url = ?", (cleaned_url,)
            ).fetchone()
            return _row_to_group(row) if row else None

    def import_from_txt(self, file_path: Path) -> int:
        """Stream URLs from a text file and insert missing groups atomically."""
        count = 0
        now = utc_now_iso()
        with self.db.transaction() as conn:
            for url in stream_urls_from_file(file_path):
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO groups (url, status, created_at, updated_at)
                    VALUES (?, 'ACTIVE', ?, ?)
                    """,
                    (url, now, now),
                )
                if cur.rowcount > 0:
                    count += 1
        return count

    def import_urls(self, urls: Iterable[str]) -> int:
        """Insert an iterable of group URLs if not already present."""
        count = 0
        now = utc_now_iso()
        with self.db.transaction() as conn:
            for raw_url in urls:
                cleaned = raw_url.strip()
                if not cleaned or cleaned.startswith("#"):
                    continue
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO groups (url, status, created_at, updated_at)
                    VALUES (?, 'ACTIVE', ?, ?)
                    """,
                    (cleaned, now, now),
                )
                if cur.rowcount > 0:
                    count += 1
        return count

    def stream_groups(
        self, status: Optional[str] = None, chunk_size: int = 100
    ) -> Generator[GroupRecord, None, None]:
        """Yield groups in bounded chunks using a database cursor."""
        with self.db.read_cursor() as cur:
            if status:
                cur.execute(
                    "SELECT * FROM groups WHERE status = ? ORDER BY id ASC",
                    (status,),
                )
            else:
                cur.execute("SELECT * FROM groups ORDER BY id ASC")
            while True:
                rows = cur.fetchmany(chunk_size)
                if not rows:
                    break
                for row in rows:
                    yield _row_to_group(row)

    def update_status(
        self, url: str, status: str, notes: Optional[str] = None
    ) -> None:
        cleaned_url = url.strip()
        now = utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE groups
                SET status = ?, notes = COALESCE(?, notes), updated_at = ?
                WHERE url = ?
                """,
                (status, notes, now, cleaned_url),
            )

    def count_groups(self) -> int:
        with self.db.read_cursor() as cur:
            row = cur.execute("SELECT COUNT(*) AS cnt FROM groups").fetchone()
            return int(row["cnt"]) if row else 0


class CampaignRepository:
    """Manages posting campaigns and active campaign selection."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def create_campaign(
        self,
        name: str,
        post_text: str,
        bundle_dir: Optional[str] = None,
        content_hash: Optional[str] = None,
        activate: bool = True,
    ) -> CampaignRecord:
        """Create a new campaign, optionally setting it as the sole active campaign."""
        now = utc_now_iso()
        resolved_hash = content_hash or compute_content_hash(post_text)
        with self.db.transaction() as conn:
            if activate:
                conn.execute("UPDATE campaigns SET is_active = 0 WHERE is_active = 1")
            cur = conn.execute(
                """
                INSERT INTO campaigns (name, bundle_dir, post_text, content_hash, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, bundle_dir, post_text, resolved_hash, 1 if activate else 0, now),
            )
            row = conn.execute(
                "SELECT * FROM campaigns WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
            assert row is not None
            return _row_to_campaign(row)

    def get_active_campaign(self) -> Optional[CampaignRecord]:
        """Return the currently active campaign, or None if none is active."""
        with self.db.read_cursor() as cur:
            row = cur.execute(
                "SELECT * FROM campaigns WHERE is_active = 1 ORDER BY id DESC LIMIT 1"
            ).fetchone()
            return _row_to_campaign(row) if row else None

    def get_by_id(self, campaign_id: int) -> Optional[CampaignRecord]:
        with self.db.read_cursor() as cur:
            row = cur.execute(
                "SELECT * FROM campaigns WHERE id = ?", (campaign_id,)
            ).fetchone()
            return _row_to_campaign(row) if row else None

    def get_or_create_for_bundle(
        self,
        name: str,
        post_text: str,
        bundle_dir: Optional[str],
        content_hash: str,
        force_new: bool = False,
    ) -> CampaignRecord:
        """Resume the active campaign if its content hash matches, else create a new one."""
        if not force_new:
            active = self.get_active_campaign()
            if active and active.content_hash == content_hash:
                return active
        return self.create_campaign(
            name=name,
            post_text=post_text,
            bundle_dir=bundle_dir,
            content_hash=content_hash,
            activate=True,
        )

    def set_active_campaign(self, campaign_id: int) -> None:
        with self.db.transaction() as conn:
            conn.execute("UPDATE campaigns SET is_active = 0 WHERE is_active = 1")
            conn.execute(
                "UPDATE campaigns SET is_active = 1 WHERE id = ?", (campaign_id,)
            )

    def list_campaigns(self, limit: int = 50) -> List[CampaignRecord]:
        with self.db.read_cursor() as cur:
            rows = cur.execute(
                "SELECT * FROM campaigns ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [_row_to_campaign(r) for r in rows]

    def list_campaigns_with_stats(self, limit: int = 100) -> List[CampaignSummary]:
        """Return campaigns along with aggregated published, pending, and URL counts."""
        with self.db.read_cursor() as cur:
            rows = cur.execute(
                """
                SELECT
                    c.*,
                    COUNT(p.id) AS total_posts,
                    SUM(CASE WHEN p.status = 'SUCCESS' THEN 1 ELSE 0 END) AS published_count,
                    SUM(CASE WHEN p.status = 'PENDING_APPROVAL' THEN 1 ELSE 0 END) AS pending_approval_count,
                    SUM(CASE WHEN p.post_url IS NOT NULL AND p.post_url != '' THEN 1 ELSE 0 END) AS with_url_count
                FROM campaigns c
                LEFT JOIN posts p ON p.campaign_id = c.id
                GROUP BY c.id
                ORDER BY c.is_active DESC, c.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            CampaignSummary(
                campaign=_row_to_campaign(r),
                total_posts=int(r["total_posts"] or 0),
                published_count=int(r["published_count"] or 0),
                pending_approval_count=int(r["pending_approval_count"] or 0),
                with_url_count=int(r["with_url_count"] or 0),
            )
            for r in rows
        ]

    def count_campaigns(self) -> int:
        with self.db.read_cursor() as cur:
            row = cur.execute("SELECT COUNT(*) AS cnt FROM campaigns").fetchone()
            return int(row["cnt"]) if row else 0


class PostRepository:
    """Manages publication results, captured post URLs, and campaign progress."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db
        self.groups = GroupRepository(db)

    def record_post(
        self,
        campaign_id: int,
        group_url: str,
        status: str,
        details: str = "",
        post_url: Optional[str] = None,
        fb_post_id: Optional[str] = None,
    ) -> PostRecord:
        """Record or update the publication result for a group within a campaign."""
        cleaned_url = group_url.strip()
        now = utc_now_iso()

        with self.db.transaction() as conn:
            group_id = self.groups.ensure_group(conn, cleaned_url)
            existing = conn.execute(
                "SELECT * FROM posts WHERE campaign_id = ? AND group_id = ?",
                (campaign_id, group_id),
            ).fetchone()

            if existing is not None:
                # Never overwrite a real published/pending post with a DRY_RUN status
                if status == "DRY_RUN" and existing["status"] in PROCESSED_STATUSES:
                    return self._fetch_post_by_id(conn, int(existing["id"]))

                conn.execute(
                    """
                    UPDATE posts
                    SET status = ?,
                        post_url = COALESCE(?, post_url),
                        fb_post_id = COALESCE(?, fb_post_id),
                        details = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (status, post_url, fb_post_id, details, now, existing["id"]),
                )
                post_id = int(existing["id"])
            else:
                cur = conn.execute(
                    """
                    INSERT INTO posts (
                        campaign_id, group_id, status, post_url, fb_post_id,
                        details, published_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        campaign_id,
                        group_id,
                        status,
                        post_url,
                        fb_post_id,
                        details,
                        now,
                        now,
                    ),
                )
                assert cur.lastrowid is not None
                post_id = int(cur.lastrowid)

            if status == "NOT_A_MEMBER":
                conn.execute(
                    "UPDATE groups SET status = 'NOT_A_MEMBER', updated_at = ? WHERE id = ?",
                    (now, group_id),
                )

            return self._fetch_post_by_id(conn, post_id)

    @staticmethod
    def _fetch_post_by_id(conn: sqlite3.Connection, post_id: int) -> PostRecord:
        row = conn.execute(
            """
            SELECT p.*, g.url AS group_url, c.name AS campaign_name
            FROM posts p
            JOIN groups g ON g.id = p.group_id
            JOIN campaigns c ON c.id = p.campaign_id
            WHERE p.id = ?
            """,
            (post_id,),
        ).fetchone()
        assert row is not None
        return _row_to_post(row)

    def get_post(self, campaign_id: int, group_url: str) -> Optional[PostRecord]:
        cleaned_url = group_url.strip()
        with self.db.read_cursor() as cur:
            row = cur.execute(
                """
                SELECT p.*, g.url AS group_url, c.name AS campaign_name
                FROM posts p
                JOIN groups g ON g.id = p.group_id
                JOIN campaigns c ON c.id = p.campaign_id
                WHERE p.campaign_id = ? AND g.url = ?
                """,
                (campaign_id, cleaned_url),
            ).fetchone()
            return _row_to_post(row) if row else None

    def is_group_processed(self, campaign_id: int, group_url: str) -> bool:
        """Return True if the group already succeeded or is pending approval in this campaign."""
        cleaned_url = group_url.strip()
        with self.db.read_cursor() as cur:
            row = cur.execute(
                """
                SELECT p.status
                FROM posts p
                JOIN groups g ON g.id = p.group_id
                WHERE p.campaign_id = ? AND g.url = ?
                """,
                (campaign_id, cleaned_url),
            ).fetchone()
            return bool(row and row["status"] in PROCESSED_STATUSES)

    def stream_posts(
        self,
        campaign_id: Optional[int] = None,
        statuses: Optional[Sequence[str]] = None,
        only_with_url: bool = False,
        chunk_size: int = 100,
    ) -> Generator[PostRecord, None, None]:
        """Yield post records ordered by most recently updated."""
        with self.db.read_cursor() as cur:
            clauses: List[str] = []
            params: List[object] = []
            if campaign_id is not None:
                clauses.append("p.campaign_id = ?")
                params.append(campaign_id)
            if statuses:
                placeholders = ",".join("?" for _ in statuses)
                clauses.append(f"p.status IN ({placeholders})")
                params.extend(statuses)
            if only_with_url:
                clauses.append("p.post_url IS NOT NULL AND p.post_url != ''")

            where_sql = f"WHERE {' AND '.join(clauses)} " if clauses else ""
            base_sql = (
                """
                SELECT p.*, g.url AS group_url, c.name AS campaign_name
                FROM posts p
                JOIN groups g ON g.id = p.group_id
                JOIN campaigns c ON c.id = p.campaign_id
                """
                + where_sql
                + "ORDER BY p.updated_at DESC"
            )
            cur.execute(base_sql, tuple(params))
            while True:
                rows = cur.fetchmany(chunk_size)
                if not rows:
                    break
                for row in rows:
                    yield _row_to_post(row)

    def stream_active_published_posts(
        self, chunk_size: int = 100
    ) -> Generator[PostRecord, None, None]:
        """Yield SUCCESS posts with captured post_url from the currently active campaign."""
        with self.db.read_cursor() as cur:
            cur.execute(
                """
                SELECT p.*, g.url AS group_url, c.name AS campaign_name
                FROM posts p
                JOIN groups g ON g.id = p.group_id
                JOIN campaigns c ON c.id = p.campaign_id
                WHERE c.is_active = 1
                  AND p.status = 'SUCCESS'
                  AND p.post_url IS NOT NULL
                  AND p.post_url != ''
                ORDER BY p.published_at DESC
                """
            )
            while True:
                rows = cur.fetchmany(chunk_size)
                if not rows:
                    break
                for row in rows:
                    yield _row_to_post(row)

    def get_campaign_stats(self, campaign_id: Optional[int] = None) -> Dict[str, int]:
        """Aggregate execution counts for a campaign (or all campaigns when None)."""
        with self.db.read_cursor() as cur:
            where_clause = "WHERE campaign_id = ?" if campaign_id is not None else ""
            params = (campaign_id,) if campaign_id is not None else ()
            rows = cur.execute(
                f"SELECT status, COUNT(*) AS cnt FROM posts {where_clause} GROUP BY status",
                params,
            ).fetchall()

        counts = {row["status"]: int(row["cnt"]) for row in rows}
        successful = counts.get("SUCCESS", 0) + counts.get("PENDING_APPROVAL", 0)
        failed = counts.get("FAILED", 0)
        skipped = counts.get("NOT_A_MEMBER", 0) + counts.get("BLOCKED", 0)
        total = sum(counts.values())
        return {
            "successful": successful,
            "success_direct": counts.get("SUCCESS", 0),
            "pending_approval": counts.get("PENDING_APPROVAL", 0),
            "failed": failed,
            "blocked": counts.get("BLOCKED", 0),
            "skipped": skipped,
            "dry_run": counts.get("DRY_RUN", 0),
            "total_recorded": total,
        }

    def get_status_map(self, campaign_id: int) -> Dict[str, PostRecord]:
        """Return mapping of group_url -> PostRecord for a given campaign."""
        return {post.group_url: post for post in self.stream_posts(campaign_id=campaign_id)}


class LegacyMigrator:
    """Non-destructive one-time importer from groups.txt and post_history.json into SQLite."""

    @staticmethod
    def migrate_if_needed(
        db: DatabaseManager,
        groups_file: Optional[Path] = None,
        history_file: Optional[Path] = None,
    ) -> Dict[str, int]:
        """Import legacy text/JSON state when SQLite has no campaigns/groups yet."""
        group_repo = GroupRepository(db)
        campaign_repo = CampaignRepository(db)
        post_repo = PostRepository(db)

        imported_groups = 0
        imported_posts = 0

        if groups_file and groups_file.exists() and group_repo.count_groups() == 0:
            imported_groups = group_repo.import_from_txt(groups_file)

        if (
            history_file
            and history_file.exists()
            and campaign_repo.count_campaigns() == 0
        ):
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    raw_history = json.load(f)
            except Exception:
                raw_history = {}

            if isinstance(raw_history, dict) and raw_history:
                legacy_campaign = campaign_repo.create_campaign(
                    name="Legacy Imported Campaign",
                    post_text="(Imported from post_history.json)",
                    bundle_dir=None,
                    content_hash="legacy_import",
                    activate=False,
                )
                for url, info in raw_history.items():
                    if not isinstance(info, dict):
                        continue
                    post_repo.record_post(
                        campaign_id=legacy_campaign.id,
                        group_url=url,
                        status=str(info.get("status", "UNKNOWN")),
                        details=str(info.get("details", "")),
                        post_url=info.get("post_url"),
                        fb_post_id=info.get("fb_post_id"),
                    )
                    imported_posts += 1

        return {
            "imported_groups": imported_groups,
            "imported_posts": imported_posts,
        }

