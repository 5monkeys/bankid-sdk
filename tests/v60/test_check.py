import pytest

import bankid_sdk
from tests.factories import TransactionFactory

pytestmark = pytest.mark.usefixtures("mock_bankid")


def test_handles_completion_when_action_is_unknown(
    sync_v60: bankid_sdk.SyncV60, valid_collect: bankid_sdk.OrderRef
) -> None:
    bankid_sdk.configure(storage=bankid_sdk.MemoryStorage(), actions=[])
    transaction = TransactionFactory()
    transaction_id = bankid_sdk.config.STORAGE.save(transaction)
    result, qr_code = bankid_sdk.check(sync_v60, transaction_id, None)
    assert isinstance(result, bankid_sdk.CompleteCollect)
    assert qr_code is None
