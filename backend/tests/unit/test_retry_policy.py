"""Unit tests for RetryPolicy dataclass."""

from dev_ghost_parser.retry_policy import RetryPolicy


class TestRetryPolicyDefaults:
    """Verify default field values."""

    def test_default_max_retries(self):
        policy = RetryPolicy()
        assert policy.max_retries == 2

    def test_default_base_delay_seconds(self):
        policy = RetryPolicy()
        assert policy.base_delay_seconds == 1.0

    def test_default_multiplier(self):
        policy = RetryPolicy()
        assert policy.multiplier == 2.0


class TestRetryPolicyCustomValues:
    """Verify custom field values are accepted."""

    def test_custom_max_retries(self):
        policy = RetryPolicy(max_retries=5)
        assert policy.max_retries == 5

    def test_custom_base_delay(self):
        policy = RetryPolicy(base_delay_seconds=0.5)
        assert policy.base_delay_seconds == 0.5

    def test_custom_multiplier(self):
        policy = RetryPolicy(multiplier=3.0)
        assert policy.multiplier == 3.0

    def test_fully_custom(self):
        policy = RetryPolicy(max_retries=1, base_delay_seconds=0.5, multiplier=3.0)
        assert policy.max_retries == 1
        assert policy.base_delay_seconds == 0.5
        assert policy.multiplier == 3.0


class TestGetDelay:
    """Verify exponential backoff delay calculation."""

    def test_attempt_zero_default(self):
        policy = RetryPolicy()
        # 1.0 * (2.0 ** 0) = 1.0
        assert policy.get_delay(0) == 1.0

    def test_attempt_one_default(self):
        policy = RetryPolicy()
        # 1.0 * (2.0 ** 1) = 2.0
        assert policy.get_delay(1) == 2.0

    def test_attempt_two_default(self):
        policy = RetryPolicy()
        # 1.0 * (2.0 ** 2) = 4.0
        assert policy.get_delay(2) == 4.0

    def test_custom_base_and_multiplier(self):
        policy = RetryPolicy(base_delay_seconds=0.5, multiplier=3.0)
        # 0.5 * (3.0 ** 0) = 0.5
        assert policy.get_delay(0) == 0.5
        # 0.5 * (3.0 ** 1) = 1.5
        assert policy.get_delay(1) == 1.5
        # 0.5 * (3.0 ** 2) = 4.5
        assert policy.get_delay(2) == 4.5

    def test_system_reporter_config(self):
        """Test with system_reporter's configuration from design doc."""
        policy = RetryPolicy(max_retries=1, base_delay_seconds=0.5, multiplier=2.0)
        assert policy.get_delay(0) == 0.5
        assert policy.get_delay(1) == 1.0
