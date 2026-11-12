"""Metadata-only operating-cost visibility; all storage is explicitly lazy."""

from .context import current_usage_context, usage_scope

__all__ = ["usage_scope", "current_usage_context", "UsageStore", "PricingTable",
           "get_usage_store", "record_usage", "get_default_pricing"]


def get_usage_store():
    from .store import get_usage_store as factory
    return factory()


def record_usage(event: dict) -> bool:
    from .store import record_usage as record
    return record(event)


def get_default_pricing():
    from .pricing import get_default_pricing as factory
    return factory()


def __getattr__(name):
    if name == "UsageStore":
        from .store import UsageStore
        return UsageStore
    if name == "PricingTable":
        from .pricing import PricingTable
        return PricingTable
    raise AttributeError(name)
