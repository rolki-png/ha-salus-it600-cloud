"""Constants for Salus iT600 Cloud integration."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

DOMAIN = "salus_it600_cloud"

# Config flow
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
# Option: mode change of one thermostat is applied to all thermostats of its gateway
CONF_SYNC_MODES = "sync_thermostat_modes"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_PUSH_SCAN_INTERVAL = "push_scan_interval"
CONF_POST_COMMAND_REFRESH_DELAY = "post_command_refresh_delay"
CONF_POLL_FAILURE_THRESHOLD = "poll_failure_threshold"

# AWS Cognito configuration
AWS_REGION = "eu-central-1"
AWS_USER_POOL_ID = "eu-central-1_XGRz3CgoY"
AWS_CLIENT_ID = "4pk5efh3v84g5dav43imsv4fbj"
AWS_IDENTITY_POOL_ID = "eu-central-1:60912c00-287d-413b-a2c9-ece3ccef9230"
AWS_IOT_ENDPOINT = "a24u3z7zzwrtdl-ats.iot.eu-central-1.amazonaws.com"

# Service API
SERVICE_API_BASE_URL = "https://service-api.eu.premium.salusconnect.io/api/v1"
COMPANY_CODE = "salus-eu"

# Polling of device states when pushed updates are unavailable (seconds)
SCAN_INTERVAL_SECONDS = 30
MIN_SCAN_INTERVAL_SECONDS = 10
MAX_SCAN_INTERVAL_SECONDS = 3600
# While device state changes are pushed over MQTT, polling is only a safety net
PUSH_SCAN_INTERVAL_SECONDS = 300
MIN_PUSH_SCAN_INTERVAL_SECONDS = 30
MAX_PUSH_SCAN_INTERVAL_SECONDS = 3600
# Gateways, devices and OneTouch rules change rarely and are re-read less often
METADATA_REFRESH_SECONDS = 900
# Entities of a device without state data for this long become unavailable
STALE_AFTER_SECONDS = 600
# Commanded state is shown until the device reports it, at most this long
PENDING_TIMEOUT_SECONDS = 60
# Without pushed state changes a command is confirmed by polling after this delay.
# The delay cannot outlive the pending window, or the commanded state disappears first.
CONFIRM_REFRESH_DELAY_SECONDS = 10
MIN_POST_COMMAND_REFRESH_DELAY_SECONDS = 1
MAX_POST_COMMAND_REFRESH_DELAY_SECONDS = PENDING_TIMEOUT_SECONDS
# Consecutive failed polls before repair logic acts
DEFAULT_POLL_FAILURE_THRESHOLD = 3
MIN_POLL_FAILURE_THRESHOLD = 1
MAX_POLL_FAILURE_THRESHOLD = 10


@dataclass(frozen=True, slots=True)
class NumberOption:
    """Integer config option with a default and inclusive bounds."""

    key: str
    default: int
    minimum: int
    maximum: int
    unit: str | None = None

    def read(self, options: Mapping[str, Any]) -> int:
        """Return the stored value, or the default, clamped into range."""
        raw = options.get(self.key, self.default)
        if isinstance(raw, bool):
            return self.default
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return self.default
        return min(self.maximum, max(self.minimum, value))


POLL_SCAN_INTERVAL = NumberOption(
    CONF_SCAN_INTERVAL,
    SCAN_INTERVAL_SECONDS,
    MIN_SCAN_INTERVAL_SECONDS,
    MAX_SCAN_INTERVAL_SECONDS,
    "s",
)
PUSH_SCAN_INTERVAL = NumberOption(
    CONF_PUSH_SCAN_INTERVAL,
    PUSH_SCAN_INTERVAL_SECONDS,
    MIN_PUSH_SCAN_INTERVAL_SECONDS,
    MAX_PUSH_SCAN_INTERVAL_SECONDS,
    "s",
)
POST_COMMAND_REFRESH_DELAY = NumberOption(
    CONF_POST_COMMAND_REFRESH_DELAY,
    CONFIRM_REFRESH_DELAY_SECONDS,
    MIN_POST_COMMAND_REFRESH_DELAY_SECONDS,
    MAX_POST_COMMAND_REFRESH_DELAY_SECONDS,
    "s",
)
POLL_FAILURE_THRESHOLD = NumberOption(
    CONF_POLL_FAILURE_THRESHOLD,
    DEFAULT_POLL_FAILURE_THRESHOLD,
    MIN_POLL_FAILURE_THRESHOLD,
    MAX_POLL_FAILURE_THRESHOLD,
)
NUMERIC_OPTIONS = (
    POLL_SCAN_INTERVAL,
    PUSH_SCAN_INTERVAL,
    POST_COMMAND_REFRESH_DELAY,
    POLL_FAILURE_THRESHOLD,
)

# Shadow device index of the gateway itself and default index of other devices
GATEWAY_SHADOW_INDEX = "000000000001"
DEFAULT_SHADOW_INDEX = "11"
