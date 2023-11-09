from __future__ import annotations

from typing import TYPE_CHECKING

from ._config import config
from .typing import TransactionID

if TYPE_CHECKING:
    from ._client import SyncV60


def cancel(client: SyncV60, transaction_id: TransactionID) -> None:
    transaction = config.STORAGE.load(transaction_id)
    if transaction is None:
        # TODO: Log
        return

    client.cancel(transaction.order_response.order_ref)
    config.STORAGE.delete(transaction_id)
