"""Unit tests for the WorkPartitioner class and BatchResult dataclass."""

from __future__ import annotations

import asyncio
import pytest

from dev_ghost_parser.work_partitioner import BatchResult, WorkPartitioner


# ---------------------------------------------------------------------------
# BatchResult dataclass tests
# ---------------------------------------------------------------------------


class TestBatchResult:
    """Tests for the BatchResult dataclass."""

    def test_successful_batch_result(self):
        result = BatchResult(
            batch_index=0,
            total_batches=3,
            success=True,
            data={"nodes": [1, 2, 3]},
            files_processed=5,
        )
        assert result.batch_index == 0
        assert result.total_batches == 3
        assert result.success is True
        assert result.data == {"nodes": [1, 2, 3]}
        assert result.error is None
        assert result.files_processed == 5

    def test_failed_batch_result(self):
        result = BatchResult(
            batch_index=2,
            total_batches=5,
            success=False,
            error="RuntimeError: parse failed",
            files_processed=0,
        )
        assert result.success is False
        assert result.data is None
        assert result.error == "RuntimeError: parse failed"
        assert result.files_processed == 0

    def test_default_values(self):
        result = BatchResult(batch_index=0, total_batches=1, success=True)
        assert result.data is None
        assert result.error is None
        assert result.files_processed == 0


# ---------------------------------------------------------------------------
# WorkPartitioner.should_partition tests
# ---------------------------------------------------------------------------


class TestShouldPartition:
    """Tests for the should_partition threshold logic."""

    def test_below_threshold_returns_false(self):
        wp = WorkPartitioner(file_threshold=50)
        assert wp.should_partition(49) is False

    def test_at_threshold_returns_false(self):
        wp = WorkPartitioner(file_threshold=50)
        assert wp.should_partition(50) is False

    def test_above_threshold_returns_true(self):
        wp = WorkPartitioner(file_threshold=50)
        assert wp.should_partition(51) is True

    def test_custom_threshold(self):
        wp = WorkPartitioner(file_threshold=10)
        assert wp.should_partition(10) is False
        assert wp.should_partition(11) is True

    def test_zero_files(self):
        wp = WorkPartitioner(file_threshold=50)
        assert wp.should_partition(0) is False


# ---------------------------------------------------------------------------
# WorkPartitioner.create_batches tests
# ---------------------------------------------------------------------------


class TestCreateBatches:
    """Tests for file batch creation."""

    def test_empty_file_list(self):
        wp = WorkPartitioner(batch_size=20)
        assert wp.create_batches([]) == []

    def test_files_less_than_batch_size(self):
        wp = WorkPartitioner(batch_size=20)
        files = [f"file{i}.py" for i in range(5)]
        batches = wp.create_batches(files)
        assert len(batches) == 1
        assert batches[0] == files

    def test_files_equal_to_batch_size(self):
        wp = WorkPartitioner(batch_size=20)
        files = [f"file{i}.py" for i in range(20)]
        batches = wp.create_batches(files)
        assert len(batches) == 1
        assert batches[0] == files

    def test_files_split_evenly(self):
        wp = WorkPartitioner(batch_size=10)
        files = [f"file{i}.py" for i in range(30)]
        batches = wp.create_batches(files)
        assert len(batches) == 3
        assert all(len(b) == 10 for b in batches)

    def test_files_split_unevenly(self):
        wp = WorkPartitioner(batch_size=10)
        files = [f"file{i}.py" for i in range(25)]
        batches = wp.create_batches(files)
        assert len(batches) == 3
        assert len(batches[0]) == 10
        assert len(batches[1]) == 10
        assert len(batches[2]) == 5

    def test_no_files_lost_or_duplicated(self):
        wp = WorkPartitioner(batch_size=7)
        files = [f"file{i}.py" for i in range(50)]
        batches = wp.create_batches(files)
        # Flatten and compare
        flat = [f for batch in batches for f in batch]
        assert flat == files
        assert len(flat) == 50


# ---------------------------------------------------------------------------
# WorkPartitioner.process_batches tests
# ---------------------------------------------------------------------------


class TestProcessBatches:
    """Tests for async batch processing."""

    @pytest.mark.asyncio
    async def test_all_batches_succeed(self):
        wp = WorkPartitioner(batch_size=5, max_batch_concurrency=3)

        async def processor(files):
            return {"count": len(files)}

        progress_calls = []

        async def progress_cb(completed, total):
            progress_calls.append((completed, total))

        files = [f"f{i}.py" for i in range(15)]
        batches = wp.create_batches(files)
        results = await wp.process_batches(batches, processor, progress_cb)

        assert len(results) == 3
        assert all(r.success for r in results)
        assert all(r.data == {"count": 5} for r in results)
        assert all(r.files_processed == 5 for r in results)
        # Progress should be called once per batch
        assert len(progress_calls) == 3

    @pytest.mark.asyncio
    async def test_failed_batch_continues_others(self):
        wp = WorkPartitioner(batch_size=5, max_batch_concurrency=3)

        async def processor(files):
            if "fail.py" in files:
                raise RuntimeError("parse error")
            return {"count": len(files)}

        progress_calls = []

        async def progress_cb(completed, total):
            progress_calls.append((completed, total))

        # Second batch will contain "fail.py"
        files = [f"f{i}.py" for i in range(5)] + ["fail.py"] + [f"g{i}.py" for i in range(4)] + [f"h{i}.py" for i in range(5)]
        batches = wp.create_batches(files)
        results = await wp.process_batches(batches, processor, progress_cb)

        assert len(results) == 3
        # First and third batch succeed
        assert results[0].success is True
        assert results[2].success is True
        # Second batch fails
        assert results[1].success is False
        assert "RuntimeError" in results[1].error
        assert results[1].files_processed == 0

    @pytest.mark.asyncio
    async def test_empty_batches(self):
        wp = WorkPartitioner()

        async def processor(files):
            return files

        async def progress_cb(completed, total):
            pass

        results = await wp.process_batches([], processor, progress_cb)
        assert results == []

    @pytest.mark.asyncio
    async def test_concurrency_is_bounded(self):
        """Verify that no more than max_batch_concurrency batches run at once."""
        max_concurrent = 2
        wp = WorkPartitioner(batch_size=3, max_batch_concurrency=max_concurrent)

        concurrent_count = 0
        max_observed = 0
        lock = asyncio.Lock()

        async def processor(files):
            nonlocal concurrent_count, max_observed
            async with lock:
                concurrent_count += 1
                max_observed = max(max_observed, concurrent_count)
            await asyncio.sleep(0.05)
            async with lock:
                concurrent_count -= 1
            return len(files)

        async def progress_cb(completed, total):
            pass

        files = [f"f{i}.py" for i in range(12)]
        batches = wp.create_batches(files)
        await wp.process_batches(batches, processor, progress_cb)

        assert max_observed <= max_concurrent


# ---------------------------------------------------------------------------
# WorkPartitioner.merge_batch_results tests
# ---------------------------------------------------------------------------


class TestMergeBatchResults:
    """Tests for batch result merging."""

    def test_all_successful(self):
        results = [
            BatchResult(batch_index=0, total_batches=2, success=True, data={"a": 1}, files_processed=10),
            BatchResult(batch_index=1, total_batches=2, success=True, data={"b": 2}, files_processed=10),
        ]
        merged = WorkPartitioner.merge_batch_results(results)
        assert merged["merged_data"] == [{"a": 1}, {"b": 2}]
        assert merged["errors"] == []
        assert merged["total_files_processed"] == 20
        assert merged["total_batches"] == 2
        assert merged["successful_batches"] == 2
        assert merged["failed_batches"] == 0
        assert merged["partial"] is False

    def test_mixed_success_and_failure(self):
        results = [
            BatchResult(batch_index=0, total_batches=3, success=True, data="ok", files_processed=5),
            BatchResult(batch_index=1, total_batches=3, success=False, error="timeout", files_processed=0),
            BatchResult(batch_index=2, total_batches=3, success=True, data="ok2", files_processed=5),
        ]
        merged = WorkPartitioner.merge_batch_results(results)
        assert merged["merged_data"] == ["ok", "ok2"]
        assert len(merged["errors"]) == 1
        assert merged["errors"][0]["batch_index"] == 1
        assert merged["errors"][0]["error"] == "timeout"
        assert merged["total_files_processed"] == 10
        assert merged["partial"] is True

    def test_all_failed(self):
        results = [
            BatchResult(batch_index=0, total_batches=2, success=False, error="err1"),
            BatchResult(batch_index=1, total_batches=2, success=False, error="err2"),
        ]
        merged = WorkPartitioner.merge_batch_results(results)
        assert merged["merged_data"] == []
        assert len(merged["errors"]) == 2
        assert merged["total_files_processed"] == 0
        assert merged["partial"] is True

    def test_empty_results(self):
        merged = WorkPartitioner.merge_batch_results([])
        assert merged["merged_data"] == []
        assert merged["errors"] == []
        assert merged["total_files_processed"] == 0
        assert merged["total_batches"] == 0
        assert merged["partial"] is False
