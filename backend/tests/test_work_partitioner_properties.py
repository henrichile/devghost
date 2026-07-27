# Feature: sub-agent-parallel-analysis, Property 8: Work Partitioning Threshold
# Feature: sub-agent-parallel-analysis, Property 9: Batch Merge Preserves Data and Annotates Failures
"""
Property 8: Work Partitioning Threshold
For any file count N and configured threshold T, should_partition(N) SHALL return
True if and only if N > T. When partitioning occurs with batch size S, the resulting
batches SHALL cover all N files with no file omitted and no file duplicated.

Property 9: Batch Merge Preserves Data and Annotates Failures
For any list of BatchResult objects where some succeed and some fail, merging them
SHALL produce a result that contains all data from successful batches and error
annotations for each failed batch, with no successful batch data lost.

**Validates: Requirements 5.1, 5.3, 5.4**
"""

from __future__ import annotations

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from dev_ghost_parser.work_partitioner import BatchResult, WorkPartitioner


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------


@st.composite
def partitioning_params(draw):
    """Generate random file_threshold, batch_size, and a file list.

    Returns a dict with:
    - file_threshold: int (1-200)
    - batch_size: int (1-50)
    - files: list[str] of unique file paths
    - file_count: int for testing should_partition
    """
    file_threshold = draw(st.integers(min_value=1, max_value=200))
    batch_size = draw(st.integers(min_value=1, max_value=50))
    num_files = draw(st.integers(min_value=0, max_value=300))
    files = [f"src/file_{i}.py" for i in range(num_files)]

    return {
        "file_threshold": file_threshold,
        "batch_size": batch_size,
        "files": files,
        "num_files": num_files,
    }


@st.composite
def batch_results_scenario(draw):
    """Generate a list of random BatchResult objects with a mix of successes and failures.

    Returns a list of BatchResult objects.
    """
    num_batches = draw(st.integers(min_value=1, max_value=20))

    results = []
    for i in range(num_batches):
        success = draw(st.booleans())
        if success:
            data = draw(
                st.one_of(
                    st.dictionaries(
                        keys=st.text(min_size=1, max_size=10),
                        values=st.integers(min_value=0, max_value=1000),
                        min_size=1,
                        max_size=5,
                    ),
                    st.lists(st.integers(), min_size=0, max_size=10),
                    st.text(min_size=1, max_size=50),
                )
            )
            files_processed = draw(st.integers(min_value=1, max_value=50))
            results.append(
                BatchResult(
                    batch_index=i,
                    total_batches=num_batches,
                    success=True,
                    data=data,
                    files_processed=files_processed,
                )
            )
        else:
            error_msg = draw(st.text(min_size=1, max_size=100))
            results.append(
                BatchResult(
                    batch_index=i,
                    total_batches=num_batches,
                    success=False,
                    error=error_msg,
                    files_processed=0,
                )
            )

    return results


# ---------------------------------------------------------------------------
# Property 8: Work Partitioning Threshold
# ---------------------------------------------------------------------------


class TestProperty8WorkPartitioningThreshold:
    """Feature: sub-agent-parallel-analysis, Property 8: Work Partitioning Threshold"""

    @settings(max_examples=100)
    @given(params=partitioning_params())
    def test_should_partition_threshold_logic(self, params):
        """For any file count N and threshold T, should_partition(N) returns
        True if and only if N > T.

        **Validates: Requirements 5.1**
        """
        wp = WorkPartitioner(
            batch_size=params["batch_size"],
            file_threshold=params["file_threshold"],
        )

        result = wp.should_partition(params["num_files"])

        if params["num_files"] > params["file_threshold"]:
            assert result is True, (
                f"should_partition({params['num_files']}) should be True "
                f"when threshold is {params['file_threshold']}"
            )
        else:
            assert result is False, (
                f"should_partition({params['num_files']}) should be False "
                f"when threshold is {params['file_threshold']}"
            )

    @settings(max_examples=100)
    @given(params=partitioning_params())
    def test_create_batches_no_file_lost(self, params):
        """When creating batches, the flattened result SHALL equal the original
        file list (no file omitted).

        **Validates: Requirements 5.1**
        """
        wp = WorkPartitioner(
            batch_size=params["batch_size"],
            file_threshold=params["file_threshold"],
        )

        batches = wp.create_batches(params["files"])

        # Flatten all batches
        flat = [f for batch in batches for f in batch]

        assert flat == params["files"], (
            f"Flattened batches do not equal original files. "
            f"Expected {len(params['files'])} files, got {len(flat)}"
        )

    @settings(max_examples=100)
    @given(params=partitioning_params())
    def test_create_batches_no_file_duplicated(self, params):
        """When files are unique, no file SHALL appear in more than one batch
        (no duplication).

        **Validates: Requirements 5.1**
        """
        wp = WorkPartitioner(
            batch_size=params["batch_size"],
            file_threshold=params["file_threshold"],
        )

        batches = wp.create_batches(params["files"])

        # Flatten all batches
        flat = [f for batch in batches for f in batch]

        # Since input files are unique (generated as file_0, file_1, ...),
        # the flattened result should also have no duplicates
        assert len(flat) == len(set(flat)), (
            f"Duplicate files found in batches. "
            f"Total files: {len(flat)}, unique: {len(set(flat))}"
        )

    @settings(max_examples=100)
    @given(params=partitioning_params())
    def test_create_batches_respects_batch_size(self, params):
        """Each batch SHALL contain at most batch_size files, and the last batch
        may contain fewer.

        **Validates: Requirements 5.1**
        """
        assume(len(params["files"]) > 0)

        wp = WorkPartitioner(
            batch_size=params["batch_size"],
            file_threshold=params["file_threshold"],
        )

        batches = wp.create_batches(params["files"])

        # All batches except possibly the last should be full
        for batch in batches[:-1]:
            assert len(batch) == params["batch_size"], (
                f"Non-last batch has {len(batch)} files, "
                f"expected {params['batch_size']}"
            )

        # Last batch should be <= batch_size
        assert len(batches[-1]) <= params["batch_size"], (
            f"Last batch has {len(batches[-1])} files, "
            f"exceeds batch_size {params['batch_size']}"
        )

        # Last batch should not be empty
        assert len(batches[-1]) > 0, "Last batch should not be empty"


# ---------------------------------------------------------------------------
# Property 9: Batch Merge Preserves Data and Annotates Failures
# ---------------------------------------------------------------------------


class TestProperty9BatchMergePreservesDataAndAnnotatesFailures:
    """Feature: sub-agent-parallel-analysis, Property 9: Batch Merge Preserves Data and Annotates Failures"""

    @settings(max_examples=100)
    @given(batch_results=batch_results_scenario())
    def test_merge_preserves_all_successful_data(self, batch_results):
        """All data from successful batches SHALL appear in merged_data.

        **Validates: Requirements 5.3, 5.4**
        """
        merged = WorkPartitioner.merge_batch_results(batch_results)

        successful_data = [r.data for r in batch_results if r.success]

        assert merged["merged_data"] == successful_data, (
            f"Merged data does not match successful batch data. "
            f"Expected {len(successful_data)} items, "
            f"got {len(merged['merged_data'])}"
        )

    @settings(max_examples=100)
    @given(batch_results=batch_results_scenario())
    def test_merge_annotates_all_failures(self, batch_results):
        """Each failed batch SHALL have an error annotation in the errors list.

        **Validates: Requirements 5.3, 5.4**
        """
        merged = WorkPartitioner.merge_batch_results(batch_results)

        failed_batches = [r for r in batch_results if not r.success]

        assert len(merged["errors"]) == len(failed_batches), (
            f"Expected {len(failed_batches)} error annotations, "
            f"got {len(merged['errors'])}"
        )

        # Each error annotation should reference the correct batch
        error_indices = {e["batch_index"] for e in merged["errors"]}
        expected_indices = {r.batch_index for r in failed_batches}

        assert error_indices == expected_indices, (
            f"Error annotation batch indices {error_indices} "
            f"do not match failed batch indices {expected_indices}"
        )

    @settings(max_examples=100)
    @given(batch_results=batch_results_scenario())
    def test_merge_total_files_processed_correct(self, batch_results):
        """total_files_processed SHALL equal the sum of files_processed from
        all successful batches.

        **Validates: Requirements 5.3, 5.4**
        """
        merged = WorkPartitioner.merge_batch_results(batch_results)

        expected_total = sum(r.files_processed for r in batch_results if r.success)

        assert merged["total_files_processed"] == expected_total, (
            f"Expected total_files_processed={expected_total}, "
            f"got {merged['total_files_processed']}"
        )

    @settings(max_examples=100)
    @given(batch_results=batch_results_scenario())
    def test_merge_partial_flag_correct(self, batch_results):
        """partial SHALL be True if any batch failed, False if all succeeded.

        **Validates: Requirements 5.3, 5.4**
        """
        merged = WorkPartitioner.merge_batch_results(batch_results)

        has_failures = any(not r.success for r in batch_results)

        assert merged["partial"] == has_failures, (
            f"Expected partial={has_failures}, got {merged['partial']}"
        )

    @settings(max_examples=100)
    @given(batch_results=batch_results_scenario())
    def test_merge_batch_counts_correct(self, batch_results):
        """successful_batches + failed_batches SHALL equal total_batches.

        **Validates: Requirements 5.3, 5.4**
        """
        merged = WorkPartitioner.merge_batch_results(batch_results)

        assert merged["total_batches"] == len(batch_results), (
            f"Expected total_batches={len(batch_results)}, "
            f"got {merged['total_batches']}"
        )

        assert merged["successful_batches"] + merged["failed_batches"] == len(batch_results), (
            f"successful_batches ({merged['successful_batches']}) + "
            f"failed_batches ({merged['failed_batches']}) != "
            f"total_batches ({len(batch_results)})"
        )

    @settings(max_examples=100)
    @given(batch_results=batch_results_scenario())
    def test_merge_no_successful_data_lost(self, batch_results):
        """No successful batch data SHALL be lost during merge — the count of
        merged_data items must equal the count of successful batches.

        **Validates: Requirements 5.3, 5.4**
        """
        merged = WorkPartitioner.merge_batch_results(batch_results)

        successful_count = sum(1 for r in batch_results if r.success)

        assert len(merged["merged_data"]) == successful_count, (
            f"Expected {successful_count} items in merged_data, "
            f"got {len(merged['merged_data'])}"
        )
