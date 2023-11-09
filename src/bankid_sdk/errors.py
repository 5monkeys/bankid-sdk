from collections.abc import Generator
from contextlib import contextmanager
from http import HTTPStatus
from types import MappingProxyType
from typing import Any, Final

import httpx


class BankIDHTTPError(Exception):
    ...


class BankIDAPIError(Exception):
    def __init__(
        self,
        *args: Any,
        response: httpx.Response | None = None,
        error_code: str = "",
        json: Any = None,
    ) -> None:
        self.code = response.status_code if response else 0
        self.response = response
        self.error_code = error_code
        self.json = json
        super().__init__(*args)


class AlreadyInProgress(BankIDAPIError):
    ...


class InvalidParameters(BankIDAPIError):
    ...


class UnknownError(BankIDAPIError):
    ...


class Unauthorized(BankIDAPIError):
    ...


class NotFound(BankIDAPIError):
    ...


class MethodNotAllowed(BankIDAPIError):
    ...


class RequestTimeout(BankIDAPIError):
    ...


class UnsupportedMediaType(BankIDAPIError):
    ...


class InternalServerError(BankIDAPIError):
    ...


class ServiceUnavailable(BankIDAPIError):
    ...


error_map: Final = MappingProxyType[tuple[int, str], type[BankIDAPIError]](
    {
        (HTTPStatus.BAD_REQUEST, "alreadyInProgress"): AlreadyInProgress,
        (HTTPStatus.BAD_REQUEST, "invalidParameters"): InvalidParameters,
        (HTTPStatus.UNAUTHORIZED, "unauthorized"): Unauthorized,
        (HTTPStatus.FORBIDDEN, "unauthorized"): Unauthorized,
        (HTTPStatus.NOT_FOUND, "notFound"): NotFound,
        (HTTPStatus.METHOD_NOT_ALLOWED, "methodNotAllowed"): MethodNotAllowed,
        (HTTPStatus.REQUEST_TIMEOUT, "requestTimeout"): RequestTimeout,
        (
            HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            "unsupportedMediaType",
        ): UnsupportedMediaType,
        (HTTPStatus.INTERNAL_SERVER_ERROR, "internalError"): InternalServerError,
        (HTTPStatus.SERVICE_UNAVAILABLE, "maintenance"): ServiceUnavailable,
    }
)


@contextmanager
def httpx_error_hook() -> Generator[None, None, None]:
    """
    An exception hook that converts;

    - Any httpx http status error to a BankIDAPIError
    - Any httpx http error to a BankIDHTTPError
    """
    try:
        yield
    except httpx.HTTPStatusError as exc:
        try:
            data = exc.response.json()
        except ValueError:
            raise UnknownError(
                response=exc.response, error_code="unknownError"
            ) from exc

        error_code = data.get("errorCode")
        Error = error_map.get((exc.response.status_code, error_code), UnknownError)
        error = Error(
            response=exc.response, error_code=error_code or "unknownError", json=data
        )
        raise error from exc
    except httpx.HTTPError as exc:
        raise BankIDHTTPError from exc
