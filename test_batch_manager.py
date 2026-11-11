"""Unit tests for GroupBatchManager backed by SQLite."""

import tempfile
import unittest
from pathlib import Path
from batch_manager import GroupBatchManager


class TestGroupBatchManager(unittest.TestCase):
    def test_batch_generator_and_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            groups_file = tmp_path / "groups.txt"
            history_file = tmp_path / "post_history.json"

            # Write 24 active URLs + comments + blank line
            lines = [
                f"# Comentario {i}" if i % 5 == 0 else f"https://www.facebook.com/groups/{i}"
                for i in range(1, 31)
            ]
            lines.insert(3, "")
            groups_file.write_text("\n".join(lines), encoding="utf-8")

            manager = GroupBatchManager(
                groups_file=groups_file,
                history_file=history_file,
                batch_size=10,
            )
            try:
                batches = list(manager.stream_batches())

                # Verify batch count: 24 active URLs -> 10 + 10 + 4 = 3 batches
                self.assertEqual(len(batches), 3)
                self.assertEqual(len(batches[0]), 10)
                self.assertEqual(len(batches[1]), 10)
                self.assertEqual(len(batches[2]), 4)

                # Simulate posting to first batch with captured post_url
                for idx, url in enumerate(batches[0]):
                    manager.record_result(
                        url,
                        status="SUCCESS",
                        post_url=f"{url}/posts/{1000 + idx}/",
                        fb_post_id=str(1000 + idx),
                    )

                # Re-stream: first 10 should be skipped
                remaining_batches = list(manager.stream_batches())
                self.assertEqual(len(remaining_batches), 2)
                self.assertEqual(len(remaining_batches[0]), 10)
                self.assertEqual(len(remaining_batches[1]), 4)

                stats = manager.get_stats()
                self.assertEqual(stats["successful"], 10)
                self.assertEqual(stats["total_recorded"], 10)
                self.assertEqual(
                    manager.history[batches[0][0]]["post_url"],
                    f"{batches[0][0]}/posts/1000/",
                )
            finally:
                manager.close()


if __name__ == "__main__":
    unittest.main()
