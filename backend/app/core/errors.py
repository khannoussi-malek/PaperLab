class DomainError(Exception):
    """Base for errors core services raise. The API maps subclasses to status codes."""


class NotFound(DomainError):
    pass


class InvalidInput(DomainError):
    pass


class Conflict(DomainError):
    """The request is valid but the resource isn't in a state that allows it (e.g. paper_not_ready)."""
