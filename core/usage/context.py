"""Request attribution only: no storage, configuration, file or network I/O."""

from contextlib import contextmanager
from contextvars import ContextVar
import re
from typing import Iterator

_SAFE_ACTIVITY = re.compile(r"[a-zA-Z0-9_.:-]{1,80}\Z")
_SAFE_ID = re.compile(r"[a-zA-Z0-9_.:-]{1,128}\Z")
_activity: ContextVar[str] = ContextVar("usage_activity", default="unattributed")
_wake_id: ContextVar[str | None] = ContextVar("usage_wake_id", default=None)


def current_usage_context() -> dict:
    """Return a new metadata-only snapshot of the current task/thread scope."""
    return {"activity": _activity.get(), "wake_id": _wake_id.get()}


@contextmanager
def usage_scope(activity: str, wake_id: str | None = None) -> Iterator[None]:
    """Attribute nested work; an omitted wake preserves the outer wake.

    Tokens are always reset, including when the operation raises. ContextVars
    isolate threads and asyncio tasks without changing the operation itself.
    """
    if not isinstance(activity, str) or not _SAFE_ACTIVITY.fullmatch(activity):
        raise ValueError("invalid activity")
    if wake_id is not None and (
        not isinstance(wake_id, str) or not _SAFE_ID.fullmatch(wake_id)
    ):
        raise ValueError("invalid wake_id")
    activity_token = _activity.set(activity)
    wake_token = _wake_id.set(_wake_id.get() if wake_id is None else wake_id)
    try:
        yield
    finally:
        _wake_id.reset(wake_token)
        _activity.reset(activity_token)
