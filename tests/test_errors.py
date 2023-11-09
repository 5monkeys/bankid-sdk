from contextlib import AbstractContextManager
from http import HTTPStatus
from typing import NoReturn

import httpx
import pytest

from bankid_sdk._client import handle_exception
from bankid_sdk.errors import BankIDHTTPError, UnknownError, httpx_error_hook


class DummyClient:
    def __init__(self) -> None:
        self.get_exc_hooks_call_count = 0

    def get_exc_hooks(self) -> list[AbstractContextManager[None]]:
        self.get_exc_hooks_call_count += 1
        return [httpx_error_hook()]


class TestHttpxErrorHook:
    async def test_async_raises_unknown_error_when_response_has_invalid_json(
        self,
    ) -> None:
        @handle_exception
        async def throw_httpx_status_error(obj: DummyClient, /) -> NoReturn:
            raise httpx.HTTPStatusError(
                HTTPStatus.BAD_REQUEST.description,
                request=httpx.Request("GET", "/"),
                response=httpx.Response(HTTPStatus.BAD_REQUEST, content=b"!notjson!"),
            )

        client = DummyClient()
        with pytest.raises(UnknownError) as exc:
            await throw_httpx_status_error(client)

        assert exc.value.response is not None
        assert exc.value.json is None
        assert client.get_exc_hooks_call_count == 1

    async def test_async_raises_bankid_http_error_on_httpx_http_error(self) -> None:
        @handle_exception
        async def throw_httpx_http_error(obj: DummyClient, /) -> NoReturn:
            raise httpx.NetworkError("net not working")

        client = DummyClient()
        with pytest.raises(BankIDHTTPError):
            await throw_httpx_http_error(client)

        assert client.get_exc_hooks_call_count == 1

    def test_sync_raises_unknown_error_when_response_has_invalid_json(self) -> None:
        @handle_exception
        def throw_httpx_status_error(obj: DummyClient, /) -> NoReturn:
            raise httpx.HTTPStatusError(
                HTTPStatus.BAD_REQUEST.description,
                request=httpx.Request("GET", "/"),
                response=httpx.Response(HTTPStatus.BAD_REQUEST, content=b"!notjson!"),
            )

        with pytest.raises(UnknownError) as exc:
            throw_httpx_status_error(DummyClient())

        assert exc.value.response is not None
        assert exc.value.json is None

    def test_sync_raises_bankid_http_error_on_httpx_http_error(self) -> None:
        @handle_exception
        def throw_httpx_http_error(obj: DummyClient, /) -> NoReturn:
            raise httpx.NetworkError("net not working")

        with pytest.raises(BankIDHTTPError):
            throw_httpx_http_error(DummyClient())
