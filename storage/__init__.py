"""SQLite persistence layer for FacebookGroupManager."""

from storage.database import DatabaseManager
from storage.models import (
    CampaignRecord,
    CampaignSummary,
    GroupRecord,
    PostRecord,
    compute_content_hash,
)
from storage.repositories import (
    CampaignRepository,
    GroupRepository,
    LegacyMigrator,
    PostRepository,
)

__all__ = [
    "CampaignRecord",
    "CampaignRepository",
    "CampaignSummary",
    "DatabaseManager",
    "GroupRecord",
    "GroupRepository",
    "LegacyMigrator",
    "PostRecord",
    "PostRepository",
    "compute_content_hash",
]

