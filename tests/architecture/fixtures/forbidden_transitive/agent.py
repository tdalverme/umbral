"""Agent reaches the forbidden application-to-infrastructure edge."""

from .application import ApplicationContract
from .domain import DomainContract


class AgentContract:
    """A marker agent contract."""

    application_contract = ApplicationContract
    domain_contract = DomainContract
