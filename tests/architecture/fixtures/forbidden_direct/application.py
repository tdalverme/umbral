"""Application coordinates domain contracts."""

from .domain import DomainContract


class ApplicationContract:
    """A marker application contract."""

    domain_contract = DomainContract
