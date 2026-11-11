"""Unit tests for SQLite persistence layer, legacy migration, and post URL parsing."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from poster import extract_fb_post_id, normalize_fb_post_url
from storage import (
    CampaignRepository,
    DatabaseManager,
    GroupRepository,
    LegacyMigrator,
    PostRepository,
    compute_content_hash,
)


class TestDatabaseAndRepositories(unittest.TestCase):
    def setUp(self) -> None:
        self.db = DatabaseManager(":memory:")
        self.groups = GroupRepository(self.db)
        self.campaigns = CampaignRepository(self.db)
        self.posts = PostRepository(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def test_schema_migrations_are_idempotent(self) -> None:
        # Calling initialize multiple times must not fail or duplicate migration rows
        self.db.initialize()
        with self.db.read_cursor() as cur:
            tables = {
                row["name"]
                for row in cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        expected = {
            "schema_migrations",
            "groups",
            "campaigns",
            "posts",
            "post_metrics_hourly",
            "comments",
            "reply_queue",
        }
        self.assertTrue(expected.issubset(tables))

    def test_group_upsert_and_streaming(self) -> None:
        urls = [f"https://www.facebook.com/groups/{i}/" for i in range(1, 16)]
        inserted = self.groups.import_urls(urls)
        self.assertEqual(inserted, 15)
        # Re-importing same URLs inserts 0 duplicates
        self.assertEqual(self.groups.import_urls(urls), 0)

        streamed = list(self.groups.stream_groups(chunk_size=4))
        self.assertEqual(len(streamed), 15)
        self.assertEqual(streamed[0].url, urls[0])

    def test_campaign_activation_and_resume_by_hash(self) -> None:
        h1 = compute_content_hash("Hola mundo", ["img1.jpg"])
        c1 = self.campaigns.get_or_create_for_bundle(
            name="Camp 1",
            post_text="Hola mundo",
            bundle_dir="bundle_1",
            content_hash=h1,
        )
        # Same hash resumes existing active campaign
        c1_resumed = self.campaigns.get_or_create_for_bundle(
            name="Camp 1",
            post_text="Hola mundo",
            bundle_dir="bundle_1",
            content_hash=h1,
        )
        self.assertEqual(c1.id, c1_resumed.id)

        # Force new campaign deactivates previous one
        c2 = self.campaigns.get_or_create_for_bundle(
            name="Camp 2",
            post_text="Hola mundo",
            bundle_dir="bundle_1",
            content_hash=h1,
            force_new=True,
        )
        self.assertNotEqual(c1.id, c2.id)
        active = self.campaigns.get_active_campaign()
        self.assertIsNotNone(active)
        assert active is not None
        self.assertEqual(active.id, c2.id)

        c1_reloaded = self.campaigns.get_by_id(c1.id)
        assert c1_reloaded is not None
        self.assertFalse(c1_reloaded.is_active)

    def test_record_post_with_url_and_active_monitoring_stream(self) -> None:
        c1 = self.campaigns.create_campaign(name="Old", post_text="Old text")
        self.posts.record_post(
            campaign_id=c1.id,
            group_url="https://www.facebook.com/groups/100/",
            status="SUCCESS",
            post_url="https://www.facebook.com/groups/100/posts/111/",
            fb_post_id="111",
        )

        # Create a new active campaign
        c2 = self.campaigns.create_campaign(name="Active", post_text="New text")
        self.posts.record_post(
            campaign_id=c2.id,
            group_url="https://www.facebook.com/groups/200/",
            status="SUCCESS",
            post_url="https://www.facebook.com/groups/200/posts/222/",
            fb_post_id="222",
        )
        self.posts.record_post(
            campaign_id=c2.id,
            group_url="https://www.facebook.com/groups/201/",
            status="PENDING_APPROVAL",
            details="Waiting for admin",
        )
        # DRY_RUN must not overwrite an existing SUCCESS post
        self.posts.record_post(
            campaign_id=c2.id,
            group_url="https://www.facebook.com/groups/200/",
            status="DRY_RUN",
            details="Simulated",
        )

        rec = self.posts.get_post(c2.id, "https://www.facebook.com/groups/200/")
        assert rec is not None
        self.assertEqual(rec.status, "SUCCESS")
        self.assertEqual(rec.post_url, "https://www.facebook.com/groups/200/posts/222/")

        # Only active campaign's SUCCESS posts with post_url should be yielded for hourly monitoring
        active_monitor_posts = list(self.posts.stream_active_published_posts())
        self.assertEqual(len(active_monitor_posts), 1)
        self.assertEqual(active_monitor_posts[0].fb_post_id, "222")

        # Campaign summaries and filtered stream_posts
        summaries = self.campaigns.list_campaigns_with_stats()
        self.assertEqual(len(summaries), 2)
        self.assertEqual(summaries[0].campaign.id, c2.id)
        self.assertEqual(summaries[0].published_count, 1)
        self.assertEqual(summaries[0].pending_approval_count, 1)
        self.assertEqual(summaries[0].with_url_count, 1)

        with_url_only = list(self.posts.stream_posts(campaign_id=c2.id, only_with_url=True))
        self.assertEqual(len(with_url_only), 1)
        self.assertEqual(with_url_only[0].fb_post_id, "222")

    def test_legacy_migration_from_txt_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            groups_txt = tmp / "groups.txt"
            groups_txt.write_text(
                "# Header\nhttps://www.facebook.com/groups/1/\nhttps://www.facebook.com/groups/2/\n",
                encoding="utf-8",
            )
            history_json = tmp / "post_history.json"
            history_json.write_text(
                json.dumps(
                    {
                        "https://www.facebook.com/groups/1/": {
                            "status": "SUCCESS",
                            "timestamp": "2026-11-10T20:00:00+00:00",
                            "details": "OK",
                        }
                    }
                ),
                encoding="utf-8",
            )

            result = LegacyMigrator.migrate_if_needed(
                self.db, groups_file=groups_txt, history_file=history_json
            )
            self.assertEqual(result["imported_groups"], 2)
            self.assertEqual(result["imported_posts"], 1)

            # Second call should be a no-op
            second = LegacyMigrator.migrate_if_needed(
                self.db, groups_file=groups_txt, history_file=history_json
            )
            self.assertEqual(second["imported_groups"], 0)
            self.assertEqual(second["imported_posts"], 0)


class TestFacebookPostUrlParser(unittest.TestCase):
    def test_extract_fb_post_id_variants(self) -> None:
        self.assertEqual(
            extract_fb_post_id("https://www.facebook.com/groups/12345/posts/987654321/"),
            "987654321",
        )
        self.assertEqual(
            extract_fb_post_id("https://www.facebook.com/groups/12345/permalink/555666777/"),
            "555666777",
        )
        self.assertEqual(
            extract_fb_post_id("https://www.facebook.com/groups/12345/?multi_permalinks=444333222"),
            "444333222",
        )
        self.assertIsNone(extract_fb_post_id("https://www.facebook.com/groups/12345/"))

    def test_normalize_fb_post_url_cleans_tracking_and_ignores_comments(self) -> None:
        raw = "/groups/1887266828711361/posts/9988776655/?__cft__[0]=abc&__tn__=%2CO%2CP-R"
        self.assertEqual(
            normalize_fb_post_url(raw),
            "https://www.facebook.com/groups/1887266828711361/posts/9988776655/",
        )
        comment_link = "https://www.facebook.com/groups/1887266828711361/posts/9988776655/?comment_id=123"
        self.assertIsNone(normalize_fb_post_url(comment_link))


if __name__ == "__main__":
    unittest.main()

