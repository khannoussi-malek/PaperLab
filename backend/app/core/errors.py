class DomainError(Exception):
    """Base for errors core services raise. The API maps subclasses to status codes."""


class NotFound(DomainError):
    pass


class InvalidInput(DomainError):
    pass
