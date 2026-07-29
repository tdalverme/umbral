"""Workers consume application and domain contracts."""

from .application import ApplicationContract
from .domain import DomainContract


class WorkerContract:
    """A marker worker contract."""

    application_contract = ApplicationContract
    domain_contract = DomainContract
