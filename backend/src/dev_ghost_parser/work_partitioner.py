"""Work partitioning utility for splitting file sets into parallel batches.

Provides the WorkPartitioner class and BatchResult dataclass used by agents
to subdivide large file processing into concurrent batches with progress
reporting and error handling.

Satisfies Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional


@dataclass
class BatchResult:
    """Result from processing a single batch within a partition.

    Satisfies Requirements 5.3, 5.4.

    Fields:
        batch_index: Zero-based index of this batch.
        total_batches: Total number of batches in the partition.
        success: Whether the batch completed without error.
        data: Batch-specific result payload (None if failed).
        error: Error description if success is False.
        files_processed: Number of files successfully processed in this batch.
    """

    batch_index: int
    total_batches: int
    success: bool
    data: Any = None
    error: Optional[str] = None
    files_processed: int = 0


class WorkPartitioner:
    """Utility for splitting file sets into parallel batches.

    Agents use this to subdivide large repositories into manageable chunks
    that are processed concurrently with bounded parallelism.

    Satisfies Requirements 5.1, 5.2, 5.3, 5.4, 5.5.

    Args:
        batch_size: Number of files per batch. Default: 20.
        file_threshold: Minimum file count to trigger partitioning. Default: 50.
        max_batch_concurrency: Maximum number of batches processed
            simultaneously via semaphore. Default: 5.
    """

    def __init__(
        self,
        batch_size: int = 20,
        file_threshold: int = 50,
        max_batch_concurrency: int = 5,
    ) -> None:
        self.batch_size = batch_size
        self.file_threshold = file_threshold
        self.max_batch_concurrency = max_batch_concurrency

    def should_partition(self, file_count: int) -> bool:
        """Return True if file count exceeds threshold.

        Satisfies Requirement 5.1: partitioning is triggered when a repository
        has more than `file_threshold` source files.

        Args:
            file_count: Number of source files in the repository.

        Returns:
            True if file_count > file_threshold, False otherwise.
        """
        return file_count > self.file_threshold

    def create_batches(self, files: list[str]) -> list[list[str]]:
        """Split files into batches of configured size.

        Guarantees that every file appears in exactly one batch (no omissions,
        no duplicates). The last batch may contain fewer files if the total
        is not evenly divisible by batch_size.

        Satisfies Requirement 5.1.

        Args:
            files: List of file paths to partition.

        Returns:
            List of batches, where each batch is a list of file paths.
            Returns an empty list if files is empty.
        """
        if not files:
            return []

        batches: list[list[str]] = []
        for i in range(0, len(files), self.batch_size):
            batches.append(files[i : i + self.batch_size])
        return batches

    async def process_batches(
        self,
        batches: list[list[str]],
        processor: Callable[[list[str]], Awaitable[Any]],
        progress_callback: Callable[[int, int], Awaitable[None]],
    ) -> list[BatchResult]:
        """Process all batches concurrently with progress reporting.

        Uses an asyncio.Semaphore to bound concurrency to
        `max_batch_concurrency`. Failed batches are recorded with error
        annotations but do not prevent other batches from completing.

        Satisfies Requirements 5.2, 5.3, 5.4, 5.5.

        Args:
            batches: List of file batches to process.
            processor: Async callable that processes a single batch of files
                and returns the result data.
            progress_callback: Async callable invoked after each batch
                completes. Receives (completed_count, total_batches).

        Returns:
            List of BatchResult objects, one per batch, in batch index order.
        """
        if not batches:
            return []

        total_batches = len(batches)
        semaphore = asyncio.Semaphore(self.max_batch_concurrency)
        completed_count = 0
        # Lock to protect completed_count increments
        count_lock = asyncio.Lock()

        async def _process_single_batch(
            batch_index: int, batch_files: list[str]
        ) -> BatchResult:
            nonlocal completed_count

            async with semaphore:
                try:
                    result_data = await processor(batch_files)
                    batch_result = BatchResult(
                        batch_index=batch_index,
                        total_batches=total_batches,
                        success=True,
                        data=result_data,
                        files_processed=len(batch_files),
                    )
                except Exception as exc:
                    error_msg = f"{type(exc).__name__}: {exc}"
                    batch_result = BatchResult(
                        batch_index=batch_index,
                        total_batches=total_batches,
                        success=False,
                        error=error_msg,
                        files_processed=0,
                    )

            # Update progress after batch completes (success or failure)
            async with count_lock:
                completed_count += 1
                current_count = completed_count

            await progress_callback(current_count, total_batches)
            return batch_result

        # Launch all batches concurrently (bounded by semaphore)
        tasks = [
            asyncio.create_task(_process_single_batch(idx, batch_files))
            for idx, batch_files in enumerate(batches)
        ]

        results = await asyncio.gather(*tasks)
        return list(results)

    @staticmethod
    def merge_batch_results(batch_results: list[BatchResult]) -> dict[str, Any]:
        """Merge batch results into a single cohesive result.

        Combines data from all successful batches and annotates failures
        with error metadata. No successful batch data is lost.

        Satisfies Requirements 5.3, 5.4.

        Args:
            batch_results: List of BatchResult objects to merge.

        Returns:
            Dictionary with:
                - "merged_data": List of data from all successful batches.
                - "errors": List of error annotations for failed batches.
                - "total_files_processed": Sum of files_processed from all
                  successful batches.
                - "total_batches": Total number of batches.
                - "successful_batches": Number of successful batches.
                - "failed_batches": Number of failed batches.
                - "partial": True if any batch failed, False if all succeeded.
        """
        merged_data: list[Any] = []
        errors: list[dict[str, Any]] = []
        total_files_processed = 0
        successful_count = 0
        failed_count = 0

        for result in batch_results:
            if result.success:
                merged_data.append(result.data)
                total_files_processed += result.files_processed
                successful_count += 1
            else:
                failed_count += 1
                errors.append(
                    {
                        "batch_index": result.batch_index,
                        "total_batches": result.total_batches,
                        "error": result.error,
                    }
                )

        return {
            "merged_data": merged_data,
            "errors": errors,
            "total_files_processed": total_files_processed,
            "total_batches": len(batch_results),
            "successful_batches": successful_count,
            "failed_batches": failed_count,
            "partial": failed_count > 0,
        }
