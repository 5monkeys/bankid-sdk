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
def _valid_auth() -> None:
    bankid_mock["auth"].return_value = httpx.Response(
        HTTPStatus.OK,
        json={
            "orderRef": "a",
            "autoStartToken": "b",
            "qrStartToken": "c",
            "qrStartSecret": "d",
        },
    )


def send_minimal_auth_request_context() -> (
    Generator[dict[str, Any], OrderResponse, None]
):
    bankid_mock["auth"].return_value = httpx.Response(
        HTTPStatus.OK,
        json={
            "orderRef": "131daac9-16c6-4618-beb0-365768f37288",
            "autoStartToken": "7c40b5c9-fa74-49cf-b98c-bfe651f9a7c6",
            "qrStartToken": "67df3917-fa0d-44e5-b327-edcc928297f8",
            "qrStartSecret": "d28db9a7-4cde-429e-a983-359be676944c",
        },
    )
    response = yield {"end_user_ip": "127.0.0.1"}
    assert response == OrderResponse(
        order_ref=OrderRef("131daac9-16c6-4618-beb0-365768f37288"),
        auto_start_token="7c40b5c9-fa74-49cf-b98c-bfe651f9a7c6",
        qr_start_token="67df3917-fa0d-44e5-b327-edcc928297f8",
        qr_start_secret="d28db9a7-4cde-429e-a983-359be676944c",
        start_time=IsDatetime,  # type: ignore[arg-type]
    )

    assert bankid_mock["auth"].call_count == 1
    request = bankid_mock["auth"].calls.last.request
    assert request.url.path == "/rp/v6.0/auth"
    assert request.headers.multi_items() == Contains(
        ("accept", "application/json"),
        ("content-type", "application/json"),
    )
    assert json.loads(request.content) == {"endUserIp": "127.0.0.1"}


async def test_can_send_minimal_auth_request_async(async_v60: AsyncV60) -> None:
    gen = send_minimal_auth_request_context()
    response = await async_v60.auth(**next(gen))
    with pytest.raises(StopIteration):
        gen.send(response)


def test_can_send_minimal_auth_request_sync(sync_v60: SyncV60) -> None:
    gen = send_minimal_auth_request_context()
    response = sync_v60.auth(**next(gen))
    with pytest.raises(StopIteration):
        gen.send(response)


@contextmanager
def send_maximal_auth_request_context() -> Generator[dict[str, Any], None, None]:
    yield {
        "end_user_ip": "127.0.0.1",
        "requirement": Requirement(
            pin_code=True,
            mrtd=True,
            card_reader="class2",
            certificate_policies=["1.2.3.4.5", "1.2.3.4.10"],
            personal_number="190000000000",
        ),
        "user_visible_data": "visible",
        "user_non_visible_data": "invisible",
        "user_visible_data_format": "simpleMarkdownV1",
    }
    assert bankid_mock["auth"].call_count == 1
    request = bankid_mock["auth"].calls.last.request
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


@pytest.mark.usefixtures("_valid_auth")
async def test_can_send_maximal_auth_request_async(async_v60: AsyncV60) -> None:
    with send_maximal_auth_request_context() as kwargs:
        await async_v60.auth(**kwargs)


@pytest.mark.usefixtures("_valid_auth")
def test_can_send_maximal_auth_request_sync(sync_v60: SyncV60) -> None:
    with send_maximal_auth_request_context() as kwargs:
        sync_v60.auth(**kwargs)


@contextmanager
def excludes_sending_requirement_if_all_options_are_none_context() -> (
    Generator[dict[str, Any], None, None]
):
    yield {"end_user_ip": "127.0.0.1", "requirement": Requirement()}
    assert bankid_mock["auth"].call_count == 1
    request = bankid_mock["auth"].calls.last.request
    assert json.loads(request.content) == {"endUserIp": "127.0.0.1"}


@pytest.mark.usefixtures("_valid_auth")
async def test_excludes_sending_requirement_if_all_options_are_none_async(
    async_v60: AsyncV60,
) -> None:
    with excludes_sending_requirement_if_all_options_are_none_context() as kwargs:
        await async_v60.auth(**kwargs)


@pytest.mark.usefixtures("_valid_auth")
def test_excludes_sending_requirement_if_all_options_are_none_sync(
    sync_v60: SyncV60,
) -> None:
    with excludes_sending_requirement_if_all_options_are_none_context() as kwargs:
        sync_v60.auth(**kwargs)


@contextmanager
def value_error_if_personal_number_exceeds_12_chars_context() -> (
    Generator[dict[str, Any], None, None]
):
    with pytest.raises(ValueError, match=r"Personal number not of length 12"):
        yield {
            "end_user_ip": "127.0.0.1",
            "requirement": Requirement(personal_number="1" * 13),
        }


async def test_raises_value_error_if_personal_number_exceeds_12_chars_async(
    async_v60: AsyncV60,
) -> None:
    with value_error_if_personal_number_exceeds_12_chars_context() as kwargs:
        await async_v60.auth(**kwargs)


def test_raises_value_error_if_personal_number_exceeds_12_chars_sync(
    sync_v60: SyncV60,
) -> None:
    with value_error_if_personal_number_exceeds_12_chars_context() as kwargs:
        sync_v60.auth(**kwargs)


@contextmanager
def value_error_if_personal_number_is_less_than_12_chars_context() -> (
    Generator[dict[str, Any], None, None]
):
    with pytest.raises(ValueError, match=r"Personal number not of length 12"):
        yield {
            "end_user_ip": "127.0.0.1",
            "requirement": Requirement(personal_number="1" * 11),
        }


async def test_raises_value_error_if_personal_number_is_less_than_12_chars_async(
    async_v60: AsyncV60,
) -> None:
    with value_error_if_personal_number_is_less_than_12_chars_context() as kwargs:
        await async_v60.auth(**kwargs)


def test_raises_value_error_if_personal_number_is_less_than_12_chars_sync(
    sync_v60: SyncV60,
) -> None:
    with value_error_if_personal_number_is_less_than_12_chars_context() as kwargs:
        sync_v60.auth(**kwargs)


@contextmanager
def value_error_if_personal_number_includes_non_digits_context() -> (
    Generator[dict[str, Any], None, None]
):
    with pytest.raises(ValueError, match=r"Personal number includes non digits"):
        yield {
            "end_user_ip": "127.0.0.1",
            "requirement": Requirement(personal_number="1" * 11 + "A"),
        }


async def test_raises_value_error_if_personal_number_includes_non_digits_async(
    async_v60: AsyncV60,
) -> None:
    with value_error_if_personal_number_includes_non_digits_context() as kwargs:
        await async_v60.auth(**kwargs)


def test_raises_value_error_if_personal_number_includes_non_digits_sync(
    sync_v60: SyncV60,
) -> None:
    with value_error_if_personal_number_includes_non_digits_context() as kwargs:
        sync_v60.auth(**kwargs)


@contextmanager
def value_error_if_encoded_user_visible_data_exceeds_1500_context() -> (
    Generator[dict[str, Any], None, None]
):
    with pytest.raises(ValueError, match=r"User data too large \(\d+\)"):
        yield {"end_user_ip": "127.0.0.1", "user_visible_data": "x" * 1126}


async def test_raises_value_error_if_encoded_user_visible_data_exceeds_1500_async(
    async_v60: AsyncV60,
) -> None:
    with value_error_if_encoded_user_visible_data_exceeds_1500_context() as kwargs:
        await async_v60.auth(**kwargs)


async def test_raises_value_error_if_encoded_user_visible_data_exceeds_1500_sync(
    sync_v60: SyncV60,
) -> None:
    with value_error_if_encoded_user_visible_data_exceeds_1500_context() as kwargs:
        sync_v60.auth(**kwargs)


@contextmanager
def value_error_if_encoded_user_non_visible_data_exceeds_1500_context() -> (
    Generator[dict[str, Any], None, None]
):
    with pytest.raises(ValueError, match=r"User data too large \(\d+\)"):
        yield {"end_user_ip": "127.0.0.1", "user_non_visible_data": "x" * 1126}


async def test_raises_value_error_if_encoded_user_non_visible_data_exceeds_1500_async(
    async_v60: AsyncV60,
) -> None:
    with value_error_if_encoded_user_non_visible_data_exceeds_1500_context() as kwargs:
        await async_v60.auth(**kwargs)


def test_raises_value_error_if_encoded_user_non_visible_data_exceeds_1500_sync(
    sync_v60: SyncV60,
) -> None:
    with value_error_if_encoded_user_non_visible_data_exceeds_1500_context() as kwargs:
        sync_v60.auth(**kwargs)
