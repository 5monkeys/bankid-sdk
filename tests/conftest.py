from collections.abc import Generator
from pathlib import Path

import httpx
import pytest
import respx

from .mocks import bankid_mock


def configure_django() -> None:
    try:
        import django
    except ImportError:  # pragma: no cover
        return

    from django.conf import settings

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


@pytest.fixture()
def mock_bankid() -> Generator[respx.Router, None, None]:
    with bankid_mock as mocked:
        yield mocked


@pytest.fixture()
def mocked_async_client(mock_bankid: respx.Router) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url="https://example.com/")


@pytest.fixture()
def mocked_sync_client(mock_bankid: respx.Router) -> httpx.Client:
    return httpx.Client(base_url="https://example.com/")


@pytest.fixture()
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"
