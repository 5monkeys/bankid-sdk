from contextlib import suppress
from datetime import timedelta
from typing import Final

from django.core import signing

from bankid_sdk.typing import TransactionID

_transaction_signer: Final = signing.TimestampSigner(
    salt="bankid_sdk.contrib.django.transaction"
)


def envelop(value: TransactionID, /) -> str:
    return _transaction_signer.sign_object(value)


def verify_envelope(value: str, /) -> TransactionID | None:
    with suppress(signing.BadSignature):
        return TransactionID(
            _transaction_signer.unsign_object(value, max_age=timedelta(minutes=5))
        )
    return None


def mask_last_four(personal_number: str) -> str:
    return personal_number[:-4] + "XXXX"
