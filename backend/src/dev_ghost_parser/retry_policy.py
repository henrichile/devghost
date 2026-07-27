"""
Retry policy configuration for sub-agent execution.

Encapsulates retry behavior with exponential backoff logic,
allowing per-agent override of retry count and delay parameters.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RetryPolicy:
    """Configuration for retry behavior of a sub-agent.

    Satisfies Requirements 4.1, 4.2, 4.5.
    """

    max_retries: int = 2
    base_delay_seconds: float = 1.0
    multiplier: float = 2.0

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for the given attempt number (0-indexed).

        The delay grows exponentially: base_delay_seconds * (multiplier ** attempt).

        Args:
            attempt: Zero-indexed retry attempt number.

        Returns:
            Delay in seconds before the next retry.
        """
        return self.base_delay_seconds * (self.multiplier ** attempt)
