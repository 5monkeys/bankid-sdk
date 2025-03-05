import bankid_sdk
from tests.factories import TransactionFactory


class TestMemoryStorage:
    def test_load_returns_none_for_unknown_key(self) -> None:
        assert bankid_sdk.MemoryStorage().load(bankid_sdk.TransactionID("ID")) is None

    def test_can_delete_transaction(self) -> None:
        transaction = TransactionFactory()
        storage = bankid_sdk.MemoryStorage()
        storage.save(transaction)
        storage.delete(transaction.transaction_id)
        assert storage.load(transaction.transaction_id) is None
