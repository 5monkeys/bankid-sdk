from __future__ import annotations

from typing import Protocol
from uuid import uuid4

from bankid_sdk.typing import TransactionID

from ._order import Transaction


class Storage(Protocol):
    def save(self, obj: Transaction, /) -> TransactionID:
        ...

    def load(self, key: TransactionID, /) -> Transaction | None:
        ...

    def delete(self, key: TransactionID, /) -> None:
        ...


class NoStorage(Storage):
    def save(self, obj: Transaction, /) -> TransactionID:
        return TransactionID(str(uuid4()))

    def load(self, key: TransactionID, /) -> Transaction | None:
        return None

    def delete(self, key: TransactionID, /) -> None:
        ...
