"""Application incorrectly reaches infrastructure."""

from .domain import DomainContract
from .infrastructure import InfrastructureContract


class ApplicationContract:
    """A marker application contract."""

    domain_contract = DomainContract
    infrastructure_contract = InfrastructureContract
