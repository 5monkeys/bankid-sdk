from __future__ import annotations

from django.core.cache import cache

import bankid_sdk


class CacheStorage:
    __slots__ = ()

    def save(self, obj: bankid_sdk.Transaction, /) -> None:
        # Kept in cache for 15min
        cache.set(key=obj.transaction_id, value=obj.as_dict(), timeout=60 * 15)

    def load(self, key: bankid_sdk.TransactionID, /) -> bankid_sdk.Transaction | None:
        obj = cache.get(key)
        if obj is not None:
            return bankid_sdk.Transaction.from_dict(obj)
        return None

    def delete(self, key: bankid_sdk.TransactionID, /) -> None:
        cache.delete(key)
