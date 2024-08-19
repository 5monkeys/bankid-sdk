from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, unique
from typing import TYPE_CHECKING, Any, Union

import httpx
from typing_extensions import TypeAlias, assert_never

from ._actions import AsyncAction
from ._config import config
from ._order import generate_qr_code
from .typing import OrderRef, PersonalNumber, TransactionID

if TYPE_CHECKING:
    from ._client import AsyncV60, SyncV60


@unique
class CollectStatus(str, Enum):
    PENDING = "pending"
    COMPLETE = "complete"
    FAILED = "failed"


@unique
class PendingHintCode(str, Enum):
    OUTSTANDING_TRANSACTION = "outstandingTransaction"
    NO_CLIENT = "noClient"
    STARTED = "started"
    USER_MRTD = "userMrtd"
    USER_CALL_CONFIRM = "userCallConfirm"
    USER_SIGN = "userSign"
    UNKNOWN = "unknown"


@unique
class FailedHintCode(str, Enum):
    EXPIRED_TRANSACTION = "expiredTransaction"
    CERTIFICATE_ERR = "certificateErr"
    USER_CANCEL = "userCancel"
    CANCELLED = "cancelled"
    START_FAILED = "startFailed"
    USER_DECLINED_CALL = "userDeclinedCall"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class User:
    personal_number: PersonalNumber
    name: str
    given_name: str
    surname: str


@dataclass(frozen=True)
class Device:
    ip_address: str
    uhi: str | None


@dataclass(frozen=True)
class StepUp:
    mrtd: bool


@dataclass(frozen=True)
class CompletionData:
    user: User
    device: Device
    bankid_issue_date: str
    step_up: StepUp | None
    signature: str
    ocsp_response: str


@dataclass(frozen=True)
class PendingCollect:
    order_ref: OrderRef
    hint_code: PendingHintCode


@dataclass(frozen=True)
class CompleteCollect:
    order_ref: OrderRef
    completion_data: CompletionData


@dataclass(frozen=True)
class FailedCollect:
    order_ref: OrderRef
    hint_code: FailedHintCode


CollectResponse: TypeAlias = Union[PendingCollect, CompleteCollect, FailedCollect]


def process_collect_response(response: httpx.Response) -> CollectResponse:
    response.raise_for_status()
    response_data: dict[str, Any] = response.json()
    status = CollectStatus(response_data["status"])
    order_ref = OrderRef(response_data["orderRef"])

    hint_code: PendingHintCode | FailedHintCode
    if status is CollectStatus.PENDING:
        try:
            hint_code = PendingHintCode(response_data["hintCode"])
        except ValueError:
            hint_code = PendingHintCode.UNKNOWN
        return PendingCollect(order_ref=order_ref, hint_code=hint_code)

    elif status is CollectStatus.COMPLETE:
        completion_data = response_data["completionData"]
        user = completion_data["user"]
        device = completion_data["device"]
        step_up = completion_data.get("stepUp")
        return CompleteCollect(
            order_ref=order_ref,
            completion_data=CompletionData(
                user=User(
                    personal_number=PersonalNumber(str(user["personalNumber"])),
                    name=str(user["name"]),
                    given_name=str(user["givenName"]),
                    surname=str(user["surname"]),
                ),
                device=Device(
                    ip_address=str(device["ipAddress"]), uhi=device.get("uhi")
                ),
                bankid_issue_date=completion_data["bankIdIssueDate"],
                step_up=StepUp(mrtd=step_up["mrtd"]) if step_up is not None else None,
                signature=completion_data["signature"],
                ocsp_response=completion_data["ocspResponse"],
            ),
        )

    elif status is CollectStatus.FAILED:
        try:
            hint_code = FailedHintCode(response_data["hintCode"])
        except ValueError:
            hint_code = FailedHintCode.UNKNOWN
        return FailedCollect(order_ref=order_ref, hint_code=hint_code)

    assert_never(status)


class TransactionExpired(Exception):
    ...


def check(
    client: SyncV60, transaction_id: TransactionID, request: Any
) -> tuple[CollectResponse, str | None]:
    transaction = config.STORAGE.load(transaction_id)
    if transaction is None:
        # TODO: Log
        raise TransactionExpired

    result = client.collect(transaction.order_response.order_ref)
    if isinstance(result, (CompleteCollect, FailedCollect)):
        # Clear transaction from storage as soon as we encounter a finished BankID
        # collection. As we can't interact with its order any longer
        config.STORAGE.delete(transaction_id)

    if isinstance(result, CompleteCollect):
        action = config.ACTIONS.get((transaction.operation, transaction.action_name))
        if action is not None:
            action().finalize(result, request, transaction.context)
        else:
            # TODO: Log error
            ...

    qr_code = None
    if isinstance(result, PendingCollect) and result.hint_code in {
        PendingHintCode.OUTSTANDING_TRANSACTION,
        PendingHintCode.NO_CLIENT,
    }:
        qr_code = generate_qr_code(transaction.order_response)

    return result, qr_code


async def acheck(
    client: AsyncV60, transaction_id: TransactionID, request: Any
) -> tuple[CollectResponse, str | None, dict[str, Any] | None]:
    # TODO: support async storage
    transaction = config.STORAGE.load(transaction_id)
    assert transaction is not None

    finalize_data = None

    result = await client.collect(transaction.order_response.order_ref)
    if isinstance(result, (CompleteCollect, FailedCollect)):
        config.STORAGE.delete(transaction_id)

    if isinstance(result, CompleteCollect):
        action = config.ACTIONS[(transaction.operation, transaction.action_name)]
        assert issubclass(action, AsyncAction)
        finalize_data = await action().finalize(result, request, transaction.context)

    qr_code = None
    if isinstance(result, PendingCollect) and result.hint_code in {
        PendingHintCode.OUTSTANDING_TRANSACTION,
        PendingHintCode.NO_CLIENT,
    }:
        qr_code = generate_qr_code(transaction.order_response)

    return result, qr_code, finalize_data
