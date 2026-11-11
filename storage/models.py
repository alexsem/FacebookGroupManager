"""Domain models and pure helpers for SQLite persistence."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional, Sequence


def compute_content_hash(post_text: str, media_names: Sequence[str] = ()) -> str:
    """Compute a deterministic SHA-256 fingerprint for a campaign bundle."""
    hasher = hashlib.sha256()
    hasher.update(post_text.strip().encode("utf-8"))
    for name in sorted(media_names):
        hasher.update(b"\x00")
        hasher.update(name.encode("utf-8"))
    return hasher.hexdigest()


@dataclass(frozen=True)
class GroupRecord:
    """Represents a Facebook group stored in SQLite."""

    id: int
    url: str
    name: Optional[str]
    status: str
    notes: Optional[str]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class CampaignRecord:
    """Represents a posting campaign tied to a PostBundle."""

    id: int
    name: str
    bundle_dir: Optional[str]
    post_text: str
    content_hash: str
    is_active: bool
    created_at: str


@dataclass(frozen=True)
class PostRecord:
    """Represents the publication outcome and URL for a group within a campaign."""

    id: int
    campaign_id: int
    group_id: int
    group_url: str
    status: str
    post_url: Optional[str]
    fb_post_id: Optional[str]
    details: str
    published_at: str
    updated_at: str
    campaign_name: Optional[str] = None


@dataclass(frozen=True)
class CampaignSummary:
    """Campaign record paired with aggregated post and URL capture counts."""

    campaign: CampaignRecord
    total_posts: int
    published_count: int
    pending_approval_count: int
    with_url_count: int

