from datetime import datetime, timezone
from uuid import uuid4

import bankid_sdk
from bankid_sdk.typing import TransactionID


def TransactionFactory() -> bankid_sdk.Transaction:
    return bankid_sdk.Transaction(
        transaction_id=TransactionID(str(uuid4())),
        order_response=bankid_sdk.OrderResponse(
            order_ref=bankid_sdk.OrderRef(str(uuid4())),
            auto_start_token=str(uuid4()),
            qr_start_token=str(uuid4()),
            qr_start_secret=str(uuid4()),
            start_time=datetime.now(tz=timezone.utc),
        ),
        operation="auth",
        action_name="ACTION",
        context={},
    )
