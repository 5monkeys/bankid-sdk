from __future__ import annotations

from contextlib import suppress
from typing import Final, Protocol
from uuid import uuid4

from ._order import Transaction
from .typing import TransactionID


class Storage(Protocol):
    def save(self, obj: Transaction, /) -> TransactionID:
        ...

    def load(self, key: TransactionID, /) -> Transaction | None:
        ...

    def delete(self, key: TransactionID, /) -> None:
        ...


class MemoryStorage:
    __slots__ = ("content",)
    NO_VALUE: Final = object()

    def __init__(self) -> None:
        self.content = dict[TransactionID, Transaction]()

    def save(self, obj: Transaction, /) -> TransactionID:
        transaction_id = TransactionID(str(uuid4()))
        self.content[transaction_id] = obj
        return transaction_id

    def load(self, key: TransactionID, /) -> Transaction | None:
        obj = self.content.get(key, self.NO_VALUE)
        if obj is not self.NO_VALUE:
            return obj  # type: ignore[return-value]
        return None

    def delete(self, key: TransactionID, /) -> None:
        with suppress(KeyError):
            del self.content[key]
