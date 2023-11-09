import json
from collections.abc import Generator
from contextlib import contextmanager
from http import HTTPStatus
from typing import Any

import httpx
import pytest
from dirty_equals import Contains, IsDatetime

from bankid_sdk import (
    AsyncV60,
    OrderRef,
    OrderResponse,
    Requirement,
    SyncV60,
)
from tests.mocks import bankid_mock

pytestmark = pytest.mark.usefixtures("mock_bankid")


@pytest.fixture()
def _valid_sign() -> None:
    bankid_mock["sign"].return_value = httpx.Response(
        HTTPStatus.OK,
        json={
            "orderRef": "a",
            "autoStartToken": "b",
            "qrStartToken": "c",
            "qrStartSecret": "d",
        },
    )


def can_send_minimal_sign_request_context() -> (
    Generator[dict[str, Any], OrderResponse, None]
):
    bankid_mock["sign"].return_value = httpx.Response(
        HTTPStatus.OK,
        json={
            "orderRef": "131daac9-16c6-4618-beb0-365768f37288",
            "autoStartToken": "7c40b5c9-fa74-49cf-b98c-bfe651f9a7c6",
            "qrStartToken": "67df3917-fa0d-44e5-b327-edcc928297f8",
            "qrStartSecret": "d28db9a7-4cde-429e-a983-359be676944c",
        },
    )
    response = yield {"end_user_ip": "127.0.0.1", "user_visible_data": "räksmörgås"}
    assert response == OrderResponse(
        order_ref=OrderRef("131daac9-16c6-4618-beb0-365768f37288"),
        auto_start_token="7c40b5c9-fa74-49cf-b98c-bfe651f9a7c6",
        qr_start_token="67df3917-fa0d-44e5-b327-edcc928297f8",
        qr_start_secret="d28db9a7-4cde-429e-a983-359be676944c",
        start_time=IsDatetime,  # type: ignore[arg-type]
    )

    assert bankid_mock["sign"].call_count == 1
    request = bankid_mock["sign"].calls.last.request
    assert request.url.path == "/rp/v6.0/sign"
    assert request.headers.multi_items() == Contains(
        ("accept", "application/json"),
        ("content-type", "application/json"),
    )
    assert json.loads(request.content) == {
        "endUserIp": "127.0.0.1",
        "userVisibleData": "csOka3Ntw7ZyZ8Olcw==",
    }


async def test_can_send_minimal_sign_request_async(async_v60: AsyncV60) -> None:
    gen = can_send_minimal_sign_request_context()
    response = await async_v60.sign(**next(gen))
    with pytest.raises(StopIteration):
        gen.send(response)


def test_can_send_minimal_sign_request_sync(sync_v60: SyncV60) -> None:
    gen = can_send_minimal_sign_request_context()
    response = sync_v60.sign(**next(gen))
    with pytest.raises(StopIteration):
        gen.send(response)


@contextmanager
def can_send_maximal_sign_request_context() -> Generator[dict[str, Any], None, None]:
    yield {
        "end_user_ip": "127.0.0.1",
        "user_visible_data": "visible",
        "requirement": Requirement(
            pin_code=True,
            mrtd=True,
            card_reader="class2",
            certificate_policies=["1.2.3.4.5", "1.2.3.4.10"],
            personal_number="190000000000",
        ),
        "user_non_visible_data": "invisible",
        "user_visible_data_format": "simpleMarkdownV1",
    }
    assert bankid_mock["sign"].call_count == 1
    request = bankid_mock["sign"].calls.last.request
    assert json.loads(request.content) == {
        "endUserIp": "127.0.0.1",
        "requirement": {
            "pinCode": True,
            "mrtd": True,
            "cardReader": "class2",
            "certificatePolicies": ["1.2.3.4.5", "1.2.3.4.10"],
            "personalNumber": "190000000000",
        },
        "userVisibleData": "dmlzaWJsZQ==",
        "userNonVisibleData": "aW52aXNpYmxl",
        "userVisibleDataFormat": "simpleMarkdownV1",
    }


@pytest.mark.usefixtures("_valid_sign")
async def test_can_send_maximal_sign_request_async(async_v60: AsyncV60) -> None:
    with can_send_maximal_sign_request_context() as kwargs:
        await async_v60.sign(**kwargs)


@pytest.mark.usefixtures("_valid_sign")
def test_can_send_maximal_sign_request_sync(sync_v60: SyncV60) -> None:
    with can_send_maximal_sign_request_context() as kwargs:
        sync_v60.sign(**kwargs)


@contextmanager
def raises_value_error_on_user_visible_data_context() -> (
    Generator[dict[str, Any], None, None]
):
    with pytest.raises(ValueError, match=r"User visible data too large \(\d+\)"):
        yield {"end_user_ip": "127.0.0.1", "user_visible_data": "x" * 40_000}


async def test_async_raises_value_error_if_encoded_user_visible_data_exceeds_40k(
    async_v60: AsyncV60,
) -> None:
    with raises_value_error_on_user_visible_data_context() as kwargs:
        await async_v60.sign(**kwargs)


def test_sync_raises_value_error_if_encoded_user_visible_data_exceeds_40k(
    sync_v60: SyncV60,
) -> None:
    with raises_value_error_on_user_visible_data_context() as kwargs:
        sync_v60.sign(**kwargs)


@contextmanager
def raises_value_error_on_user_non_visible_data_context() -> (
    Generator[dict[str, Any], None, None]
):
    with pytest.raises(ValueError, match=r"User non visible data too large \(\d+\)"):
        yield {
            "end_user_ip": "127.0.0.1",
            "user_visible_data": "1",
            "user_non_visible_data": "x" * 200_000,
        }


async def test_async_raises_value_error_if_encoded_user_non_visible_data_exceeds_200k(
    async_v60: AsyncV60,
) -> None:
    with raises_value_error_on_user_non_visible_data_context() as kwargs:
        await async_v60.sign(**kwargs)


def test_sync_raises_value_error_if_encoded_user_non_visible_data_exceeds_200k(
    sync_v60: SyncV60,
) -> None:
    with raises_value_error_on_user_non_visible_data_context() as kwargs:
        sync_v60.sign(**kwargs)
