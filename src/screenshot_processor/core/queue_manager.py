"""Queue Manager for organizing and managing screenshot processing queues.

This module provides the QueueManager class that organizes ProcessingResults
into queues based on their metadata tags, enabling efficient batch operations
and queue-based workflow management.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import ProcessingResult
    from .queue_models import ProcessingMetadata, ProcessingTag, ScreenshotQueue


class QueueStatistics:
    """Statistics for a processing queue."""

    def __init__(self, queue_name: str) -> None:
        """Initialize queue statistics.

        Args:
            queue_name: Name of the queue
        """
        self.queue_name = queue_name
        self.total_count = 0
        self.with_title = 0
        self.without_title = 0
        self.avg_accuracy_diff: float | None = None
        self.image_paths: list[str] = []

    def to_dict(self) -> dict:
        """Convert statistics to dictionary.

        Returns:
            Dictionary representation of statistics
        """
        return {
            "queue_name": self.queue_name,
            "total_count": self.total_count,
            "with_title": self.with_title,
            "without_title": self.without_title,
            "avg_accuracy_diff": self.avg_accuracy_diff,
            "image_count": len(self.image_paths),
        }


class QueueManager:
    """Manager for organizing screenshots into queues based on processing metadata.

    The QueueManager provides:
    - Automatic queue assignment based on metadata tags
    - Queue filtering and retrieval
    - Queue statistics and reporting
    - Batch operations on queues

    Example:
        >>> manager = QueueManager()
        >>> for result in processing_results:
        ...     manager.add_result(result)
        >>>
        >>> # Get all screenshots needing review
        >>> needs_review = manager.get_queue(ScreenshotQueue.NEEDS_REVIEW_CLOSE)
        >>> print(f"Found {len(needs_review)} screenshots needing review")
        >>>
        >>> # Get statistics
        >>> stats = manager.get_statistics()
        >>> for queue_name, queue_stats in stats.items():
        ...     print(f"{queue_name}: {queue_stats.total_count} screenshots")
    """

    def __init__(self) -> None:
        """Initialize the queue manager."""
        # Queue name -> list of ProcessingResults
        self._queues: dict[str, list[ProcessingResult]] = defaultdict(list)

        # Track all results for global operations
        self._all_results: list[ProcessingResult] = []

    def add_result(self, result: ProcessingResult) -> None:
        """Add a processing result to the appropriate queue.

        The queue is determined from the result's metadata tags.
        If no metadata is present, the result is added to UNPROCESSED.

        Args:
            result: ProcessingResult to add to queue
        """
        from .queue_models import ScreenshotQueue

        self._all_results.append(result)

        if result.metadata:
            queue_name = result.metadata.queue.value
        else:
            queue_name = ScreenshotQueue.UNPROCESSED.value

        self._queues[queue_name].append(result)

    def add_results(self, results: list[ProcessingResult]) -> None:
        """Add multiple processing results to queues.

        Args:
            results: List of ProcessingResults to add
        """
        for result in results:
            self.add_result(result)

    def get_queue(self, queue: ScreenshotQueue | str) -> list[ProcessingResult]:
        """Get all results in a specific queue.

        Args:
            queue: Queue to retrieve (ScreenshotQueue enum or string)

        Returns:
            List of ProcessingResults in the queue (empty if queue doesn't exist)
        """
        from .queue_models import ScreenshotQueue

        if isinstance(queue, ScreenshotQueue):
            queue_name = queue.value
        else:
            queue_name = queue

        return self._queues.get(queue_name, [])

    def get_all_queues(self) -> dict[str, list[ProcessingResult]]:
        """Get all queues and their contents.

        Returns:
            Dictionary mapping queue names to lists of ProcessingResults
        """
        return dict(self._queues)

    def get_queue_names(self) -> list[str]:
        """Get names of all non-empty queues.

        Returns:
            List of queue names that contain at least one result
        """
        return list(self._queues.keys())

    def get_queue_count(self, queue: ScreenshotQueue | str) -> int:
        """Get the number of results in a queue.

        Args:
            queue: Queue to count (ScreenshotQueue enum or string)

        Returns:
            Number of results in the queue
        """
        return len(self.get_queue(queue))

    def get_total_count(self) -> int:
        """Get total number of results across all queues.

        Returns:
            Total number of results
        """
        return len(self._all_results)

    def get_statistics(self) -> dict[str, QueueStatistics]:
        """Get detailed statistics for all queues.

        Returns:
            Dictionary mapping queue names to QueueStatistics objects
        """
        from .queue_models import ProcessingTag

        stats: dict[str, QueueStatistics] = {}

        for queue_name, results in self._queues.items():
            queue_stats = QueueStatistics(queue_name)
            queue_stats.total_count = len(results)
            queue_stats.image_paths = [r.image_path for r in results]

            accuracy_diffs: list[float] = []

            for result in results:
                if result.metadata:
                    # Check for title
                    if ProcessingTag.TITLE_NOT_FOUND.value not in result.metadata.tags:
                        queue_stats.with_title += 1
                    else:
                        queue_stats.without_title += 1

                    # Collect accuracy differences
                    if result.metadata.accuracy_diff_minutes is not None:
                        accuracy_diffs.append(result.metadata.accuracy_diff_minutes)

            # Calculate average accuracy difference
            if accuracy_diffs:
                queue_stats.avg_accuracy_diff = sum(accuracy_diffs) / len(accuracy_diffs)

            stats[queue_name] = queue_stats

        return stats

    def get_results_by_tag(self, tag: ProcessingTag | str) -> list[ProcessingResult]:
        """Get all results that have a specific tag.

        Args:
            tag: Tag to search for (ProcessingTag enum or string)

        Returns:
            List of ProcessingResults with the specified tag
        """
        from .queue_models import ProcessingTag

        if isinstance(tag, ProcessingTag):
            tag_value = tag.value
        else:
            tag_value = tag

        results = []
        for result in self._all_results:
            if result.metadata and tag_value in result.metadata.tags:
                results.append(result)

        return results

    def get_results_needing_review(self) -> list[ProcessingResult]:
        """Get all results that need manual review.

        Returns:
            List of ProcessingResults from NEEDS_REVIEW_CLOSE and NEEDS_REVIEW_POOR queues
        """
        from .queue_models import ScreenshotQueue

        close_matches = self.get_queue(ScreenshotQueue.NEEDS_REVIEW_CLOSE)
        poor_matches = self.get_queue(ScreenshotQueue.NEEDS_REVIEW_POOR)

        return close_matches + poor_matches

    def get_auto_processed_results(self) -> list[ProcessingResult]:
        """Get all successfully auto-processed results.

        Returns:
            List of ProcessingResults from AUTO_FIXED and AUTO_ANCHOR queues
        """
        from .queue_models import ScreenshotQueue

        fixed_grid = self.get_queue(ScreenshotQueue.AUTO_FIXED)
        anchor_method = self.get_queue(ScreenshotQueue.AUTO_ANCHOR)

        return fixed_grid + anchor_method

    def get_failed_results(self) -> list[ProcessingResult]:
        """Get all failed processing results.

        Returns:
            List of ProcessingResults from FAILED_EXTRACTION and FAILED_NO_TOTAL queues
        """
        from .queue_models import ScreenshotQueue

        extraction_failed = self.get_queue(ScreenshotQueue.FAILED_EXTRACTION)
        no_total = self.get_queue(ScreenshotQueue.FAILED_NO_TOTAL)

        return extraction_failed + no_total

    def clear(self) -> None:
        """Clear all queues and results."""
        self._queues.clear()
        self._all_results.clear()

    def remove_result(self, image_path: str) -> bool:
        """Remove a result from its queue by image path.

        Args:
            image_path: Path to the image to remove

        Returns:
            True if result was found and removed, False otherwise
        """
        # Find and remove from all_results
        for i, result in enumerate(self._all_results):
            if result.image_path == image_path:
                self._all_results.pop(i)
                break
        else:
            return False  # Not found

        # Find and remove from queue
        for _queue_name, results in self._queues.items():
            for i, result in enumerate(results):
                if result.image_path == image_path:
                    results.pop(i)
                    return True

        return False

    def update_result(self, image_path: str, new_metadata: ProcessingMetadata) -> bool:
        """Update a result's metadata and move it to the appropriate queue.

        Args:
            image_path: Path to the image to update
            new_metadata: New metadata to assign

        Returns:
            True if result was found and updated, False otherwise
        """
        # Find the result
        target_result = None
        for result in self._all_results:
            if result.image_path == image_path:
                target_result = result
                break

        if not target_result:
            return False

        # Remove from old queue
        if target_result.metadata:
            old_queue = target_result.metadata.queue.value
            old_queue_results = self._queues.get(old_queue, [])
            if target_result in old_queue_results:
                old_queue_results.remove(target_result)

        # Update metadata
        target_result.metadata = new_metadata

        # Add to new queue
        new_queue = new_metadata.queue.value
        self._queues[new_queue].append(target_result)

        return True

    def print_summary(self) -> None:
        """Print a formatted summary of all queues."""
        from .queue_models import ScreenshotQueue

        print("=" * 78)
        print("QUEUE MANAGER SUMMARY")
        print("=" * 78)
        print()
        print(f"Total Screenshots: {self.get_total_count()}")
        print(f"Active Queues: {len(self._queues)}")
        print()

        # Define queue order for display
        queue_order = [
            ScreenshotQueue.AUTO_FIXED,
            ScreenshotQueue.AUTO_ANCHOR,
            ScreenshotQueue.NEEDS_REVIEW_CLOSE,
            ScreenshotQueue.NEEDS_REVIEW_POOR,
            ScreenshotQueue.FAILED_NO_TOTAL,
            ScreenshotQueue.FAILED_EXTRACTION,
            ScreenshotQueue.DAILY,
            ScreenshotQueue.VALIDATED,
            ScreenshotQueue.REJECTED,
            ScreenshotQueue.UNPROCESSED,
        ]

        stats = self.get_statistics()

        for queue in queue_order:
            queue_name = queue.value
            if queue_name in stats:
                queue_stats = stats[queue_name]
                print(f"{queue_name:35} {queue_stats.total_count:>5} screenshots")
                if queue_stats.avg_accuracy_diff is not None:
                    print(f"{'':35} Avg diff: {queue_stats.avg_accuracy_diff:>5.1f} min")

        print()
        print("=" * 78)
