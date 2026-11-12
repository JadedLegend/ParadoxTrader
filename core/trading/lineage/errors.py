"""Typed failures at the durable lineage boundary."""


class LineageError(ValueError):
    """Invalid or unsupported lineage input."""


class LineageConflict(LineageError):
    """An idempotency, reference, or confirmed-state conflict."""


class LineageAccessError(LineageError):
    """Caller lacks explicit owner/operator access."""


class LineageNotFound(LineageError):
    """The requested lineage record does not exist."""
