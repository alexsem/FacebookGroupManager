"""Unit tests for GroupBatchManager."""

import tempfile
from pathlib import Path
from batch_manager import GroupBatchManager


def test_batch_generator_and_state():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        groups_file = tmp_path / "groups.txt"
        history_file = tmp_path / "post_history.json"

        # Write 25 groups (including blank lines and comments)
        lines = [f"# Comentario {i}" if i % 5 == 0 else f"https://www.facebook.com/groups/{i}" for i in range(1, 31)]
        lines.insert(3, "")
        groups_file.write_text("\n".join(lines), encoding="utf-8")

        # Initialize batch manager with batch_size = 10
        manager = GroupBatchManager(
            groups_file=groups_file,
            history_file=history_file,
            batch_size=10,
        )

        batches = list(manager.stream_batches())

        # Verify batch count: 24 active URLs -> 10 + 10 + 4 = 3 batches
        assert len(batches) == 3, f"Expected 3 batches, got {len(batches)}"
        assert len(batches[0]) == 10
        assert len(batches[1]) == 10
        assert len(batches[2]) == 4

        # Simulate posting to first batch
        for url in batches[0]:
            manager.record_result(url, status="SUCCESS")

        # Re-stream: first 10 should be skipped
        remaining_batches = list(manager.stream_batches())
        assert len(remaining_batches) == 2
        assert len(remaining_batches[0]) == 10
        assert len(remaining_batches[1]) == 4

        stats = manager.get_stats()
        assert stats["successful"] == 10
        assert stats["total_recorded"] == 10
        print("All GroupBatchManager tests passed successfully!")


if __name__ == "__main__":
    test_batch_generator_and_state()
