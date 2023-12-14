from __future__ import annotations

import hashlib
import hmac
import json
from base64 import b64encode
from collections.abc import Generator
from contextlib import AbstractContextManager, contextmanager
from datetime import timedelta
from http import HTTPStatus
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from dirty_equals import IsPartialDict, IsStr, IsUUID
from django.core.signing import TimestampSigner
from django.test import override_settings
from django.test.client import Client
from django.urls import reverse, reverse_lazy
from freezegun import freeze_time

import bankid_sdk
from bankid_sdk.contrib.django.storage import CacheStorage
from tests.mocks import bankid_mock


class DjangoLoginAction(bankid_sdk.AuthAction):
    name = "LOGIN"

    def initialize(
        self, request: Any, context: Any
    ) -> tuple[bankid_sdk.UserAuthData, dict[str, Any] | None]:
        auth_data = bankid_sdk.UserAuthData(
            visible="dummy_login_action_visible_auth_data",
            non_visible="dummy_login_action_non_visible_auth_data",
            visible_format=None,
        )
        return auth_data, context

    def finalize(
        self, response: bankid_sdk.CompleteCollect, request: Any, context: Any
    ) -> None:
        return None


class ForbiddenAction(bankid_sdk.AuthAction):
    name = "FORBIDDEN_ACTION"

    def initialize(
        self, request: Any, context: Any
    ) -> tuple[bankid_sdk.UserAuthData, dict[str, Any] | None]:
        raise bankid_sdk.InitFailed(
            detail="This action is forbidden", status=HTTPStatus.FORBIDDEN
        )

    def finalize(
        self, response: bankid_sdk.CompleteCollect, request: Any, context: Any
    ) -> None:
        ...


class FailsInitAction(bankid_sdk.AuthAction):
    name = "FAILS_INIT_ACTION"

    def initialize(
        self, request: Any, context: Any
    ) -> tuple[bankid_sdk.UserAuthData, dict[str, Any] | None]:
        raise bankid_sdk.InitFailed

    def finalize(
        self, response: bankid_sdk.CompleteCollect, request: Any, context: Any
    ) -> None:
        ...


class FailsFinalizeAction(bankid_sdk.AuthAction):
    name = "FAILS_FINALIZE_ACTION"

    def initialize(
        self, request: Any, context: Any
    ) -> tuple[bankid_sdk.UserAuthData, dict[str, Any] | None]:
        return (
            bankid_sdk.UserAuthData(
                visible=None, non_visible=None, visible_format=None
            ),
            None,
        )

    def finalize(
        self, response: bankid_sdk.CompleteCollect, request: Any, context: Any
    ) -> None:
        raise bankid_sdk.FinalizeFailed


@pytest.fixture()
def _configure_bankid_sdk(fixtures_dir: Path) -> None:
    bankid_sdk.configure(
        api_base_url="https://example.com",
        storage=CacheStorage(),
        actions=[
            DjangoLoginAction,
            FailsInitAction,
            ForbiddenAction,
            FailsFinalizeAction,
        ],
        certificate=(
            str(fixtures_dir / "fake_cert.pem"),
            str(fixtures_dir / "fake_client.key"),
        ),
        ca_cert=str(fixtures_dir / "fake_cacert.crt"),
    )


pytestmark = pytest.mark.usefixtures("mock_bankid", "_configure_bankid_sdk")


endpoints = pytest.mark.parametrize(
    "url",
    [
        pytest.param(reverse_lazy("auth"), id="auth"),
        # TODO: pytest.param(reverse_lazy("sign"), id="sign"),
        pytest.param(reverse_lazy("check"), id="check"),
        pytest.param(reverse_lazy("cancel"), id="cancel"),
    ],
)


@pytest.mark.parametrize(
    "method",
    # TODO: Use http.HTTPMethod once >= 3.11
    ["CONNECT", "DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "PUT", "TRACE"],
)
@endpoints
def test_disallowed_http_method(client: Client, url: str, method: str) -> None:
    response = client.generic(method, url, data={}, content_type="application/json")
    assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED
    assert response.headers.get("Allow") == "POST"
    if method == "HEAD":
        assert response.headers.get("Content-Type") == "text/plain"
    else:
        assert response.headers.get("Content-Type") == "application/json"
        assert response.json() == {"detail": f"Method {method!r} not allowed"}


@endpoints
def test_tells_to_never_cache_on(client: Client, url: str) -> None:
    response = client.post(url, data={}, content_type="application/json")
    cache_control = response.headers.get("Cache-Control")
    assert cache_control == "max-age=0, no-cache, no-store, must-revalidate, private"


@endpoints
def test_returns_unprocessable_entity_when_non_dictionary_in_body(
    client: Client, url: str
) -> None:
    response = client.post(url, data=[], content_type="application/json")
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@endpoints
def test_is_csrf_exempt_on(url: str) -> None:
    with override_settings(
        INSTALLED_APPS=["django.contrib.auth", "django.contrib.contenttypes"],
        MIDDLEWARE=[
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.middleware.csrf.CsrfViewMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
        ],
    ):
        client = Client(enforce_csrf_checks=True)
        response = client.post(url, data={}, content_type="application/json")
        # Not being a 403 or 405 means that the request passed through csrf checking
        assert response.status_code not in {
            HTTPStatus.FORBIDDEN,
            HTTPStatus.METHOD_NOT_ALLOWED,
        }
        assert response.headers.get("Content-Type") == "application/json"


class TestAuth:
    def test_picks_up_client_ip_from_x_forwarded_for_header(
        self, client: Client
    ) -> None:
        bankid_mock["auth"].return_value = httpx.Response(
            HTTPStatus.OK,
            json={
                "orderRef": "a",
                "autoStartToken": "b",
                "qrStartToken": "c",
                "qrStartSecret": "d",
            },
        )
        response = client.post(
            reverse("auth"),
            data={"action": "LOGIN", "context": None},
            content_type="application/json",
            HTTP_X_FORWARDED_FOR="192.168.1.1",
        )
        assert response.status_code == HTTPStatus.OK
        assert bankid_mock["auth"].call_count == 1
        assert json.loads(
            bankid_mock["auth"].calls.last.request.content
        ) == IsPartialDict(endUserIp="192.168.1.1")

    def test_returns_bad_request_for_invalid_client_ip(self, client: Client) -> None:
        response = client.post(
            reverse("auth"),
            data={"action": "LOGIN", "context": None},
            content_type="application/json",
            HTTP_X_FORWARDED_FOR="abc",
        )
        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.json() == {"detail": "Invalid IP"}

    @pytest.mark.parametrize(
        ("data", "errors"),
        [
            pytest.param(
                {},
                [
                    {
                        "loc": ["action"],
                        "msg": "field required",
                        "type": "value_error.missing",
                    }
                ],
                id="when_action_is_missing",
            ),
            pytest.param(
                {"action": None},
                [{"loc": ["action"], "msg": "invalid value", "type": "value_error"}],
                id="when_action_is_none",
            ),
        ],
    )
    def test_returns_unprocessable_entity(
        self, client: Client, data: dict[str, Any], errors: list[dict[str, Any]]
    ) -> None:
        response = client.post(
            reverse("auth"), data=data, content_type="application/json"
        )
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert response.json() == {"detail": errors}

    def test_custom_status_and_details_in_init_failed_are_returned_in_response(
        self, client: Client
    ) -> None:
        response = client.post(
            reverse("auth"),
            data={"action": "FORBIDDEN_ACTION"},
            content_type="application/json",
        )
        assert response.status_code == HTTPStatus.FORBIDDEN
        assert response.json() == {"detail": "This action is forbidden"}

    def test_default_status_and_details_in_init_failed_are_returned_in_response(
        self, client: Client
    ) -> None:
        response = client.post(
            reverse("auth"),
            data={"action": "FAILS_INIT_ACTION"},
            content_type="application/json",
        )
        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.json() == {"detail": "Initialisation failed"}

    def test_returns_service_unavailable_if_bankid_responds_with_client_error(
        self, client: Client
    ) -> None:
        bankid_mock["auth"].return_value = httpx.Response(
            HTTPStatus.BAD_REQUEST, json={"errorCode": "invalidParameters"}
        )
        response = client.post(
            reverse("auth"), data={"action": "LOGIN"}, content_type="application/json"
        )
        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert response.json() == {"detail": "Service unavailable"}
        assert response.headers.get("Retry-After") == "1"

    def test_returns_service_unavailable_for_http_error_in_bankid_client(
        self, client: Client
    ) -> None:
        bankid_mock["auth"].side_effect = httpx.NetworkError("net not working")
        response = client.post(
            reverse("auth"), data={"action": "LOGIN"}, content_type="application/json"
        )
        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert response.json() == {"detail": "Service unavailable"}
        assert response.headers.get("Retry-After") == "1"


class TestCheck:
    @pytest.mark.parametrize(
        ("data", "errors"),
        [
            pytest.param(
                {},
                [
                    {
                        "loc": ["transaction_id"],
                        "msg": "field required",
                        "type": "value_error.missing",
                    }
                ],
                id="when_transaction_id_is_missing",
            ),
            pytest.param(
                {"transaction_id": None},
                [
                    {
                        "loc": ["transaction_id"],
                        "msg": "invalid value",
                        "type": "value_error",
                    }
                ],
                id="when_transaction_id_is_none",
            ),
        ],
    )
    def test_returns_unprocessable_entity(
        self, client: Client, data: dict[str, Any], errors: list[dict[str, Any]]
    ) -> None:
        response = client.post(
            reverse("check"), data=data, content_type="application/json"
        )
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert response.json() == {"detail": errors}


@contextmanager
def does_call(*routes: tuple[respx.Route, int]) -> Generator[None, None, None]:
    expected_counts = [
        (route.name, route.call_count + extra) for route, extra in routes
    ]
    yield
    assert [(route.name, route.call_count) for route, _ in routes] == expected_counts


def doesnt_call(*routes: respx.Route) -> AbstractContextManager[None]:
    # Simply syntactic sugar for 'does_call' zero (0) times
    return does_call(*((route, 0) for route in routes))


class TestAuthFlow:
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

    def test_can_retrieve_completed(self, client: Client) -> None:
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
        with freeze_time("2023-01-01T12:00:00+01:00") as frozen_time:
            transaction_id = self.start_auth_login_action(client)
            frozen_time.tick(timedelta(seconds=1))
            self.check_transaction_is_pending(
                client,
                transaction_id,
                hint_code="outstandingTransaction",
                qr_code=IsStr(min_length=1),
            )
            frozen_time.tick(timedelta(seconds=1))
            self.check_transaction_is_pending(
                client, transaction_id, hint_code="started", qr_code=None
            )
            frozen_time.tick(timedelta(seconds=1))
            self.check_transaction_is_complete(client, transaction_id)
            self.verify_transaction_is_consumed(client, transaction_id)

    def start_auth(self, client: Client, body: dict[str, Any]) -> str:
        with does_call((bankid_mock["auth"], 1)):
            response = client.post(
                reverse("auth"),
                data=body,
                content_type="application/json",
                REMOTE_ADDR="192.168.1.1",
            )
            assert response.status_code == HTTPStatus.OK

        response_data = response.json()
        assert response_data == {
            "transaction_id": IsStr(min_length=1),
            "auto_start_token": IsStr(min_length=1),
        }
        payload = TimestampSigner(
            salt="bankid_sdk.contrib.django.transaction"
        ).unsign_object(response_data["transaction_id"])
        assert payload == IsUUID(4)

        call = bankid_mock["auth"].calls.last
        assert (
            response_data["auto_start_token"] == call.response.json()["autoStartToken"]
        )

        return str(response_data["transaction_id"])

    def start_auth_login_action(self, client: Client) -> str:
        transaction_id = self.start_auth(
            client, body={"action": "LOGIN", "context": None}
        )
        call = bankid_mock["auth"].calls.last
        assert json.loads(call.request.content) == IsPartialDict(
            endUserIp="192.168.1.1",
            userVisibleData=b64encode(b"dummy_login_action_visible_auth_data").decode(),
            userNonVisibleData=b64encode(
                b"dummy_login_action_non_visible_auth_data"
            ).decode(),
        )
        return transaction_id

    def check_transaction_is_pending(
        self, client: Client, transaction_id: str, hint_code: str, qr_code: Any
    ) -> None:
        check_data = {"transaction_id": transaction_id}
        with does_call((bankid_mock["collect"], 1)):
            response = client.post(
                reverse("check"), data=check_data, content_type="application/json"
            )
            assert response.status_code == HTTPStatus.OK

        auth_response_data = bankid_mock["auth"].calls.last.response.json()

        response_data = response.json()
        if qr_code is not None:
            assert response_data == {
                "status": "pending",
                "hint_code": hint_code,
                "qr_code": qr_code,
            }
            # Find a QR code built on a 1 second delta (per frozen time)
            assert response_data["qr_code"] == ".".join(
                [
                    "bankid",
                    auth_response_data["qrStartToken"],
                    "1",
                    hmac.new(
                        auth_response_data["qrStartSecret"].encode(),
                        b"1",
                        hashlib.sha256,
                    ).hexdigest(),
                ]
            )
        else:
            assert response_data == {"status": "pending", "hint_code": hint_code}

        collect_request = bankid_mock["collect"].calls.last.request
        assert json.loads(collect_request.content) == {
            "orderRef": auth_response_data["orderRef"]
        }

    def check_transaction_is_complete(
        self, client: Client, transaction_id: str
    ) -> None:
        check_data = {"transaction_id": transaction_id}
        with does_call((bankid_mock["collect"], 1)):
            response = client.post(
                reverse("check"), data=check_data, content_type="application/json"
            )
            assert response.status_code == HTTPStatus.OK

        response_data = response.json()
        assert response_data == {
            "status": "complete",
            "order": {
                "user": {
                    "name": IsStr,
                    "given_name": IsStr,
                    "surname": IsStr,
                    "personal_number": IsStr(regex=r"^\d+X{4}$"),
                },
            },
        }

    def test_can_cancel_initiated(self, client: Client) -> None:
        self.valid_auth()
        # Only respond once from cancel
        bankid_mock["cancel"].side_effect = [httpx.Response(HTTPStatus.OK, json={})]
        transaction_id = self.start_auth_login_action(client)
        self.cancel_transaction(client, transaction_id)
        self.verify_transaction_is_consumed(client, transaction_id)

    def cancel_transaction(self, client: Client, transaction_id: str) -> None:
        with does_call((bankid_mock["cancel"], 1)):
            response = client.post(
                reverse("cancel"),
                data={"transaction_id": transaction_id},
                content_type="application/json",
            )
            assert response.status_code == HTTPStatus.NO_CONTENT

        assert response.headers.get("Content-Type") == "application/json"

        auth_response_data = bankid_mock["auth"].calls.last.response.json()
        cancel_request = bankid_mock["cancel"].calls.last.request
        assert json.loads(cancel_request.content) == {
            "orderRef": auth_response_data["orderRef"]
        }

    def verify_transaction_is_consumed(
        self, client: Client, transaction_id: str
    ) -> None:
        data = {"transaction_id": transaction_id}
        with doesnt_call(bankid_mock["cancel"], bankid_mock["collect"]):
            # While a cancel request still might return success, BankID's cancel
            # shouldn't be called if transaction is already consumed.
            response = client.post(
                reverse("cancel"), data=data, content_type="application/json"
            )
            assert response.status_code == HTTPStatus.NO_CONTENT
            # Test post a collect request
            response = client.post(
                reverse("check"), data=data, content_type="application/json"
            )
            assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
            assert response.json() == {
                "detail": [
                    {
                        "loc": ["transaction_id"],
                        "msg": "transaction expired",
                        "type": "value_error.expired",
                    }
                ]
            }

    def test_can_retrieve_failed(self, client: Client) -> None:
        order_ref = self.valid_auth()
        # Only respond with success once from collect
        bankid_mock["collect"].side_effect = [
            httpx.Response(
                HTTPStatus.OK,
                json={
                    "orderRef": order_ref,
                    "status": "failed",
                    "hintCode": "expiredTransaction",
                },
            ),
        ]
        transaction_id = self.start_auth_login_action(client)
        self.check_transaction_is_failed(client, transaction_id)
        self.verify_transaction_is_consumed(client, transaction_id)

    def check_transaction_is_failed(self, client: Client, transaction_id: str) -> None:
        check_data = {"transaction_id": transaction_id}
        with does_call((bankid_mock["collect"], 1)):
            response = client.post(
                reverse("check"), data=check_data, content_type="application/json"
            )
            assert response.status_code == HTTPStatus.OK

        response_data = response.json()
        assert response_data == {"status": "failed", "hint_code": "expiredTransaction"}

    def test_returns_bad_request_if_action_finalize_fails(self, client: Client) -> None:
        order_ref = self.valid_auth()
        bankid_mock["collect"].return_value = httpx.Response(
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
        )

        # Init succeeds
        transaction_id = self.start_auth(
            client, body={"action": "FAILS_FINALIZE_ACTION"}
        )
        # BankID collect succeeds but action finalization fails
        check_data = {"transaction_id": transaction_id}
        with does_call((bankid_mock["collect"], 1)):
            response = client.post(
                reverse("check"), data=check_data, content_type="application/json"
            )
            assert response.status_code == HTTPStatus.BAD_REQUEST
            assert response.json() == {"detail": "Completion failed"}
        # Ensure we clear transaction traces, since BankID responded with success
        self.verify_transaction_is_consumed(client, transaction_id)
