import json
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date
from http import HTTPStatus
from typing import TypeAlias

import httpx
import pytest
from dirty_equals import Contains

from bankid_sdk import (
    AsyncV60,
    CompleteCollect,
    CompletionData,
    Device,
    FailedCollect,
    FailedHintCode,
    OrderRef,
    PendingCollect,
    PendingHintCode,
    PersonalNumber,
    SyncV60,
    User,
)
from tests.mocks import bankid_mock

CollectReturn: TypeAlias = PendingCollect | CompleteCollect | FailedCollect
pytestmark = pytest.mark.usefixtures("mock_bankid")


@contextmanager
def can_send_collect_request_context() -> Generator[OrderRef, None, None]:
    bankid_mock["collect"].return_value = httpx.Response(
        HTTPStatus.OK,
        json={
            "orderRef": "ref",
            "status": "pending",
            "hintCode": "outstandingTransaction",
        },
    )

    yield OrderRef("ref")

    assert bankid_mock["collect"].call_count == 1
    request = bankid_mock["collect"].calls.last.request
    assert request.url.path == "/rp/v6.0/collect"
    assert request.headers.multi_items() == Contains(
        ("accept", "application/json"),
        ("content-type", "application/json"),
    )
    assert json.loads(request.content) == {"orderRef": "ref"}


async def test_can_send_collect_request_async(async_v60: AsyncV60) -> None:
    with can_send_collect_request_context() as order_ref:
        await async_v60.collect(order_ref)


def test_can_send_collect_request_sync(sync_v60: SyncV60) -> None:
    with can_send_collect_request_context() as order_ref:
        sync_v60.collect(order_ref)


def can_collect_completed_context() -> Generator[OrderRef, CollectReturn, None]:
    bankid_mock["collect"].return_value = httpx.Response(
        HTTPStatus.OK,
        json={
            "orderRef": "ref",
            "status": "complete",
            "completionData": {
                "user": {
                    "personalNumber": "190000000000",
                    "name": "John Smith",
                    "givenName": "John",
                    "surname": "Smith",
                },
                "device": {"ipAddress": "127.0.0.1"},
                "bankIdIssueDate": "2023-01-01",
                "signature": "base64",
                "ocspResponse": "base64",
            },
        },
    )
    response = yield OrderRef("ref")

    assert isinstance(response, CompleteCollect)
    assert response == CompleteCollect(
        order_ref=OrderRef("ref"),
        completion_data=CompletionData(
            user=User(
                personal_number=PersonalNumber("190000000000"),
                name="John Smith",
                given_name="John",
                surname="Smith",
            ),
            device=Device(ip_address="127.0.0.1", uhi=None),
            bankid_issue_date=date(2023, 1, 1),
            step_up=None,
            signature="base64",
            ocsp_response="base64",
        ),
    )


async def test_async_can_collect_completed(async_v60: AsyncV60) -> None:
    gen = can_collect_completed_context()
    response = await async_v60.collect(next(gen))
    with pytest.raises(StopIteration):
        gen.send(response)


def test_sync_can_collect_completed(sync_v60: SyncV60) -> None:
    gen = can_collect_completed_context()
    response = sync_v60.collect(next(gen))
    with pytest.raises(StopIteration):
        gen.send(response)


pending_collect_code_cases = pytest.mark.parametrize(
    ("hint_code", "expected"),
    [
        pytest.param("outstandingTransaction", PendingHintCode.OUTSTANDING_TRANSACTION),
        pytest.param("noClient", PendingHintCode.NO_CLIENT),
        pytest.param("started", PendingHintCode.STARTED),
        pytest.param("userMrtd", PendingHintCode.USER_MRTD),
        pytest.param("userCallConfirm", PendingHintCode.USER_CALL_CONFIRM),
        pytest.param("userSign", PendingHintCode.USER_SIGN),
        pytest.param(
            "xyz", PendingHintCode.UNKNOWN, id="unknown_for_unknown_hint_code"
        ),
    ],
)


@pending_collect_code_cases
async def test_async_pending_collect_can_recognise_hint_code(
    async_v60: AsyncV60, hint_code: str, expected: PendingHintCode
) -> None:
    bankid_mock["collect"].return_value = httpx.Response(
        HTTPStatus.OK,
        json={"orderRef": "ref", "status": "pending", "hintCode": hint_code},
    )
    response = await async_v60.collect(OrderRef("ref"))
    assert isinstance(response, PendingCollect)
    assert response.hint_code == expected


@pending_collect_code_cases
def test_sync_pending_collect_can_recognise_hint_code(
    sync_v60: SyncV60, hint_code: str, expected: PendingHintCode
) -> None:
    bankid_mock["collect"].return_value = httpx.Response(
        HTTPStatus.OK,
        json={"orderRef": "ref", "status": "pending", "hintCode": hint_code},
    )
    response = sync_v60.collect(OrderRef("ref"))
    assert isinstance(response, PendingCollect)
    assert response.hint_code == expected


failed_collect_code_cases = pytest.mark.parametrize(
    ("hint_code", "expected"),
    [
        pytest.param("expiredTransaction", FailedHintCode.EXPIRED_TRANSACTION),
        pytest.param("certificateErr", FailedHintCode.CERTIFICATE_ERR),
        pytest.param("userCancel", FailedHintCode.USER_CANCEL),
        pytest.param("cancelled", FailedHintCode.CANCELLED),
        pytest.param("startFailed", FailedHintCode.START_FAILED),
        pytest.param("userDeclinedCall", FailedHintCode.USER_DECLINED_CALL),
        pytest.param("xyz", FailedHintCode.UNKNOWN, id="unknown_for_unknown_hint_code"),
    ],
)


def failed_collect_context(
    hint_code: str, expected: FailedHintCode
) -> Generator[OrderRef, CollectReturn, None]:
    bankid_mock["collect"].return_value = httpx.Response(
        HTTPStatus.OK,
        json={"orderRef": "ref", "status": "failed", "hintCode": hint_code},
    )
    response = yield OrderRef("ref")
    assert isinstance(response, FailedCollect)
    assert response.hint_code == expected


@failed_collect_code_cases
async def test_async_failed_collect_can_recognise_hint_code(
    async_v60: AsyncV60, hint_code: str, expected: FailedHintCode
) -> None:
    gen = failed_collect_context(hint_code, expected)
    response = await async_v60.collect(next(gen))
    with pytest.raises(StopIteration):
        gen.send(response)


@failed_collect_code_cases
def test_sync_failed_collect_can_recognise_hint_code(
    sync_v60: SyncV60, hint_code: str, expected: FailedHintCode
) -> None:
    gen = failed_collect_context(hint_code, expected)
    response = sync_v60.collect(next(gen))
    with pytest.raises(StopIteration):
        gen.send(response)
