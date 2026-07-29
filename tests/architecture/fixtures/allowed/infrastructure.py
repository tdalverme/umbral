"""Infrastructure adapts application and domain contracts."""

from .application import ApplicationContract
from .domain import DomainContract


class InfrastructureContract:
    """A marker infrastructure adapter."""

    application_contract = ApplicationContract
    domain_contract = DomainContract
