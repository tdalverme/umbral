"""API consumes application and domain contracts."""

from .application import ApplicationContract
from .domain import DomainContract


class ApiContract:
    """A marker API contract."""

    application_contract = ApplicationContract
    domain_contract = DomainContract
