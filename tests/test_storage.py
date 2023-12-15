import bankid_sdk


class TestMemoryStorage:
    def test_load_returns_none_for_unknown_key(self) -> None:
        assert bankid_sdk.MemoryStorage().load(bankid_sdk.TransactionID("ID")) is None
