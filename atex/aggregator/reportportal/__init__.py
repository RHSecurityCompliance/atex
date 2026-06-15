# this also exposes 'api' for APIError, etc.
from .api import ReportPortalAPI
from .reportportal import ReportPortalAggregator, get_existing_tests

__all__ = (
    "ReportPortalAggregator",
    "ReportPortalAPI",
    "get_existing_tests",
)
