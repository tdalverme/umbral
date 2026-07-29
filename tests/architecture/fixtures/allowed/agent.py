"""Agent consumes application and domain contracts."""

from .application import ApplicationContract
from .domain import DomainContract


class AgentContract:
    """A marker agent contract."""

    application_contract = ApplicationContract
    domain_contract = DomainContract
