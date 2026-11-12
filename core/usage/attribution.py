"""Context-only attribution; wrapping an activity never records spending."""
from functools import wraps
import re
from uuid import uuid4

from .context import usage_scope


_LABEL = re.compile(r'[a-zA-Z0-9_.:-]{1,80}\Z')


def attribute_activity(activity=None, *, action_arg=None, new_wake=False):
    """Tag provider calls nested within a function, preserving its signature.

    The activity itself is not a billable event. Quiet rest, cooldowns, and
    failures before an HTTP request therefore create no spending records.
    """
    def decorate(function):
        @wraps(function)
        def attributed(*args, **kwargs):
            label = activity
            if action_arg is not None:
                label = kwargs.get('action', args[action_arg] if len(args) > action_arg else None)
            if not isinstance(label, str) or not _LABEL.fullmatch(label):
                label = 'unsupported_action'
            supplied_wake = kwargs.get('wake_id')
            wake_id = (str(uuid4()) if supplied_wake is None else supplied_wake) if new_wake else None
            with usage_scope(label, wake_id=wake_id):
                return function(*args, **kwargs)
        return attributed
    return decorate
