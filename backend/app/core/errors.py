class DomainError(Exception):
    """Base for errors core services raise. The API maps subclasses to status codes.

    `details` carry what a caller can act on, e.g. NotFound("unknown_workspace", available=[...]). The MCP server
    returns them to the model as `{"error": code, **details}`.
    """

    def __init__(self, message: str = "", **details):
        super().__init__(message)
        self.details = details


class NotFound(DomainError):
    pass


class InvalidInput(DomainError):
    pass


class Conflict(DomainError):
    """The request is valid but the resource isn't in a state that allows it (e.g. paper_not_ready)."""
