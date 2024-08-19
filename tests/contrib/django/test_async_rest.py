from __future__ import annotations

import json
from collections.abc import Generator
from http import HTTPStatus
from pathlib import Path
from typing import Any
from unittest import mock

import httpx
import pytest
from dirty_equals import IsPartialDict
from django.test.client import AsyncClient
from django.urls import reverse

import bankid_sdk
from bankid_sdk import FailedHintCode
from bankid_sdk.contrib.django.storage import CacheStorage
from tests.mocks import bankid_mock


class AsyncDjangoLoginAction(bankid_sdk.AsyncAuthAction):
    name = "ASYNC_LOGIN"

    async def initialize(
        self, request: Any, context: Any
    ) -> tuple[bankid_sdk.UserAuthData, dict[str, Any] | None]:
        auth_data = bankid_sdk.UserAuthData(
            visible="dummy_login_action_visible_auth_data",
            non_visible="dummy_login_action_non_visible_auth_data",
            visible_format=None,
        )
        return auth_data, context

    async def finalize(
        self, response: bankid_sdk.CompleteCollect, request: Any, context: Any
    ) -> dict[str, Any]:
        return {"foo": "bar"}


class FailsInitAction(bankid_sdk.AsyncAuthAction):
    name = "FAILS_INIT_ACTION"

    async def initialize(
        self, request: Any, context: Any
    ) -> tuple[bankid_sdk.UserAuthData, dict[str, Any] | None]:
        raise bankid_sdk.InitFailed

    async def finalize(
        self, response: bankid_sdk.CompleteCollect, request: Any, context: Any
    ) -> None:
        ...


class FailsFinalizeAction(bankid_sdk.AsyncAuthAction):
    name = "FAILS_FINALIZE_ACTION"

    async def initialize(
        self, request: Any, context: Any
    ) -> tuple[bankid_sdk.UserAuthData, dict[str, Any] | None]:
        return (
            bankid_sdk.UserAuthData(
                visible=None, non_visible=None, visible_format=None
            ),
            None,
        )

    async def finalize(
        self, response: bankid_sdk.CompleteCollect, request: Any, context: Any
    ) -> None:
        raise bankid_sdk.FinalizeFailed


@pytest.fixture()
def _configure_bankid_sdk(fixtures_dir: Path) -> None:
    bankid_sdk.configure(
        api_base_url="https://example.com",
        storage=CacheStorage(),
        actions=[AsyncDjangoLoginAction, FailsInitAction, FailsFinalizeAction],
        certificate=(
            str(fixtures_dir / "fake_cert.pem"),
            str(fixtures_dir / "fake_client.key"),
        ),
        ca_cert=str(fixtures_dir / "fake_cacert.crt"),
    )


pytestmark = pytest.mark.usefixtures("mock_bankid", "_configure_bankid_sdk")


@pytest.fixture()
def _mocked_sleep() -> Generator[None, None, None]:
    with mock.patch("asyncio.sleep", autospec=True):
        yield


@pytest.mark.usefixtures("_mocked_sleep")
class TestAsyncAuth:
    def valid_auth(self) -> str:
        order_ref = "131daac9-16c6-4618-beb0-365768f37288"
        bankid_mock["auth"].return_value = httpx.Response(
            HTTPStatus.OK,
            json={
                "orderRef": order_ref,
                "autoStartToken": "7c40b5c9-fa74-49cf-b98c-bfe651f9a7c6",
                "qrStartToken": "67df3917-fa0d-44e5-b327-edcc928297f8",
                "qrStartSecret": "d28db9a7-4cde-429e-a983-359be676944c",
            },
        )
        return order_ref

    async def test_successful_auth_flow(self, async_client: AsyncClient) -> None:
        order_ref = self.valid_auth()
        bankid_mock["collect"].side_effect = [
            httpx.Response(
                HTTPStatus.OK,
                json={
                    "orderRef": order_ref,
                    "status": "pending",
                    "hintCode": "outstandingTransaction",
                },
            ),
            httpx.Response(
                HTTPStatus.OK,
                json={
                    "orderRef": order_ref,
                    "status": "pending",
                    "hintCode": "started",
                },
            ),
            httpx.Response(
                HTTPStatus.OK,
                json={
                    "orderRef": order_ref,
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
                        "signature": "base64(<visible-data>...</visible-data>)",
                        "ocspResponse": "base64",
                    },
                },
            ),
        ]
        response = await async_client.post(
            reverse("async_auth"),
            data={"action": "ASYNC_LOGIN", "context": {"some": "value"}},
            content_type="application/json",
            headers={"X-Forwarded-For": "192.168.1.1"},
        )
        assert response.status_code == 200
        events = [data async for data in response.streaming_content]  # type: ignore[attr-defined]
        assert b"event: auth" in events[0]

        assert b"event: pending" in events[1]
        assert b"outstandingTransaction" in events[1]

        assert b"event: pending" in events[2]
        assert b"started" in events[2]

        assert b"event: complete" in events[3]
        assert b'"finalize_data": {"foo": "bar"}' in events[3]

        assert json.loads(
            bankid_mock["auth"].calls.last.request.content
        ) == IsPartialDict(endUserIp="192.168.1.1")

    async def test_auth_flow_fails_with_invalid_ip(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.post(
            reverse("async_auth"),
            data={"action": "ASYNC_LOGIN", "context": {"some": "value"}},
            content_type="application/json",
            headers={"X-Forwarded-For": "foo"},
        )
        events = [data async for data in response.streaming_content]  # type: ignore[attr-defined]
        assert b"event: failed" in events[0]
        assert b'"detail": "Invalid IP"' in events[0]

    @pytest.mark.parametrize(
        "data",
        [
            pytest.param(
                {},
                id="when_action_is_missing",
            ),
            pytest.param(
                {"action": "banan"},
                id="when_action_is_none",
            ),
        ],
    )
    async def test_returns_unprocessable_entity(
        self,
        async_client: AsyncClient,
        data: dict[str, Any],
    ) -> None:
        response = await async_client.post(
            reverse("async_auth"),
            data=data,
            content_type="application/json",
        )
        events = [data async for data in response.streaming_content]  # type: ignore[attr-defined]
        assert b"event: failed" in events[0]
        assert b"Invalid action" in events[0]

    async def test_custom_status_and_details_if_init_failed_is_returned_in_response(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.post(
            reverse("async_auth"),
            data={"action": "FAILS_INIT_ACTION"},
            content_type="application/json",
        )
        events = [data async for data in response.streaming_content]  # type: ignore[attr-defined]
        assert b"event: failed" in events[0]
        assert b"Initialisation failed" in events[0]

    async def test_custom_status_and_details_if_finalize_failed_is_returned_in_response(
        self, async_client: AsyncClient
    ) -> None:
        order_ref = self.valid_auth()
        bankid_mock["collect"].side_effect = [
            httpx.Response(
                HTTPStatus.OK,
                json={
                    "orderRef": order_ref,
                    "status": "pending",
                    "hintCode": "outstandingTransaction",
                },
            ),
            httpx.Response(
                HTTPStatus.OK,
                json={
                    "orderRef": order_ref,
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
                        "signature": "base64(<visible-data>...</visible-data>)",
                        "ocspResponse": "base64",
                    },
                },
            ),
        ]
        response = await async_client.post(
            reverse("async_auth"),
            data={"action": "FAILS_FINALIZE_ACTION"},
            content_type="application/json",
        )
        assert response.status_code == 200
        events = [data async for data in response.streaming_content]  # type: ignore[attr-defined]
        assert b"event: auth" in events[0]

        assert b"event: pending" in events[1]
        assert b"outstandingTransaction" in events[1]

        assert b"event: failed" in events[2]
        assert b'"detail": "Completion failed"' in events[2]

    async def test_returns_service_unavailable_if_bankid_responds_with_client_error(
        self, async_client: AsyncClient
    ) -> None:
        bankid_mock["auth"].return_value = httpx.Response(
            HTTPStatus.BAD_REQUEST, json={"errorCode": "invalidParameters"}
        )
        response = await async_client.post(
            reverse("async_auth"),
            data={"action": "ASYNC_LOGIN"},
            content_type="application/json",
        )
        events = [data async for data in response.streaming_content]  # type: ignore[attr-defined]
        assert b"event: failed" in events[0]
        assert b'"detail": "Service unavailable"' in events[0]

    async def test_streams_failed_event_if_bankid_collect_fails(
        self, async_client: AsyncClient
    ) -> None:
        order_ref = self.valid_auth()
        bankid_mock["collect"].side_effect = [
            httpx.Response(
                HTTPStatus.OK,
                json={
                    "orderRef": order_ref,
                    "status": "pending",
                    "hintCode": "outstandingTransaction",
                },
            ),
            httpx.Response(
                HTTPStatus.OK,
                json={
                    "orderRef": order_ref,
                    "status": "failed",
                    "hintCode": FailedHintCode.START_FAILED,
                },
            ),
        ]
        response = await async_client.post(
            reverse("async_auth"),
            data={"action": "ASYNC_LOGIN"},
            content_type="application/json",
        )

        events = [data async for data in response.streaming_content]  # type: ignore[attr-defined]

        assert b"event: auth" in events[0]

        assert b"event: pending" in events[1]
        assert b"outstandingTransaction" in events[1]

        assert b"event: failed" in events[2]
        assert b'"hint_code": "startFailed"' in events[2]

    async def test_fails_with_wrong_content_type(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.post(
            reverse("async_auth"),
            data={"action": "ASYNC_LOGIN"},
            content_type="text/plain",
        )
        assert response.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
        assert response.json() == {
            "detail": "Unsupported media type 'text/plain' in request"
        }

    async def test_can_continue_active_transaction(
        self, async_client: AsyncClient
    ) -> None:
        order_ref = self.valid_auth()
        bankid_mock["collect"].side_effect = [
            httpx.Response(
                HTTPStatus.OK,
                json={
                    "orderRef": order_ref,
                    "status": "pending",
                    "hintCode": "started",
                },
            ),
            httpx.Response(
                HTTPStatus.OK,
                json={
                    "orderRef": order_ref,
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
                        "signature": "base64(<visible-data>...</visible-data>)",
                        "ocspResponse": "base64",
                    },
                },
            ),
        ]

        response = await async_client.post(
            reverse("async_auth"),
            data={"action": "ASYNC_LOGIN", "context": {"some": "value"}},
            content_type="application/json",
            headers={"X-Forwarded-For": "192.168.1.1"},
        )
        assert response.status_code == 200
        event = await response.streaming_content.__anext__()  # type: ignore[attr-defined]
        assert b"event: auth" in event
        data = event.decode("utf-8").split("data: ")[1]
        transaction_id = json.loads(data)["transaction_id"]

        response = await async_client.post(
            reverse("async_auth"),
            data={"transaction_id": transaction_id},
            content_type="application/json",
            headers={"X-Forwarded-For": "192.168.1.1"},
        )

        assert response.status_code == 200
        events = [data async for data in response.streaming_content]  # type: ignore[attr-defined]
        assert b"event: pending" in events[1]
        assert b"started" in events[1]

        assert b"event: complete" in events[2]
        assert b'"finalize_data": {"foo": "bar"}' in events[2]

    async def test_can_not_continue_invalid_transaction(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.post(
            reverse("async_auth"),
            data={"transaction_id": "invalid-value"},
            content_type="application/json",
            headers={"X-Forwarded-For": "192.168.1.1"},
        )
        assert response.status_code == 200
        events = [data async for data in response.streaming_content]  # type: ignore[attr-defined]
        assert b"event: failed" in events[0]
        assert b'"detail": "Invalid transaction"' in events[0]
