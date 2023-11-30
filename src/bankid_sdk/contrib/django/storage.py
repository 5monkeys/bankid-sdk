from __future__ import annotations

from uuid import uuid4

from django.core.cache import cache

from bankid_sdk import Transaction
from bankid_sdk.typing import TransactionID


class CacheStorage:
    def save(self, obj: Transaction, /) -> TransactionID:
        transaction_id = TransactionID(str(uuid4()))
        # Kept in cache for 15min
        cache.set(key=transaction_id, value=obj.as_dict(), timeout=60 * 15)
        return transaction_id

    def load(self, key: TransactionID, /) -> Transaction | None:
        obj = cache.get(key)
        if obj is not None:
            return Transaction.from_dict(obj)
        return None

    def delete(self, key: TransactionID, /) -> None:
        cache.delete(key)
