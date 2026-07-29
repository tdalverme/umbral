"""Domain directly reaches infrastructure: a forbidden edge."""

from .infrastructure import InfrastructureContract


class DomainContract:
    """A marker domain contract."""

    infrastructure_contract = InfrastructureContract
