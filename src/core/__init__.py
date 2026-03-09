class AuthError(Exception):
    """Base exception for auth service."""
    def __init__(self, message: str, details: list[str] | None = None):
        self.message = message
        self.details = details
        super().__init__(message)


class AuthenticationError(AuthError):
    """401 — Invalid credentials, expired token."""
    pass


class AuthorizationError(AuthError):
    """403 — Insufficient permissions."""
    pass


class ValidationError(AuthError):
    """422 — Invalid input."""
    pass


class ConflictError(AuthError):
    """409 — Duplicate resource."""
    pass


class NotFoundError(AuthError):
    """404 — Resource not found."""
    pass


class AccountLockedError(AuthError):
    """423 — Account locked due to failed attempts."""
    def __init__(self, message: str, locked_until: str | None = None):
        self.locked_until = locked_until
        super().__init__(message)
