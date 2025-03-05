import pytest

import bankid_sdk
from bankid_sdk._collect import ActionNotFoundError
from tests.factories import TransactionFactory

pytestmark = pytest.mark.usefixtures("mock_bankid")


def test_action_not_found_error_is_raised_when_action_is_unknown(
    sync_v60: bankid_sdk.SyncV60, valid_collect: bankid_sdk.OrderRef
) -> None:
    bankid_sdk.configure(storage=bankid_sdk.MemoryStorage(), actions=[])
    transaction = TransactionFactory()
    bankid_sdk.config.STORAGE.save(transaction)
    with pytest.raises(ActionNotFoundError):
        bankid_sdk.check(sync_v60, transaction.transaction_id, None)
