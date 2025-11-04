from collections.abc import Generator
from http import HTTPStatus
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import respx

import bankid_sdk

from .mocks import bankid_mock


def configure_django() -> None:
    try:
        import django  # noqa: PLC0415
    except ImportError:  # pragma: no cover
        return

    from django.conf import settings  # noqa: PLC0415

    settings.configure(
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": ":memory:",
            }
        },
        SECRET_KEY="supersecret",
        PASSWORD_HASHERS=("django.contrib.auth.hashers.MD5PasswordHasher",),
        ROOT_URLCONF="tests.contrib.django.urls",
    )
    django.setup()


def pytest_configure(config: pytest.Config) -> None:
    configure_django()


@pytest.fixture
def mock_bankid() -> Generator[respx.Router, None, None]:
    with bankid_mock as mocked:
        yield mocked


@pytest.fixture
def mocked_async_client(mock_bankid: respx.Router) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url="https://example.com/")


@pytest.fixture
def mocked_sync_client(mock_bankid: respx.Router) -> httpx.Client:
    return httpx.Client(base_url="https://example.com/")


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def valid_collect() -> bankid_sdk.OrderRef:
    order_ref = bankid_sdk.OrderRef(str(uuid4()))
    bankid_mock["collect"].side_effect = [
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
    bankid_mock["collect"].return_value = httpx.Response(
        HTTPStatus.BAD_REQUEST, json={"errorCode": "invalidParameters"}
    )
    return order_ref
