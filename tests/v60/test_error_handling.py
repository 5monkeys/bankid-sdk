from collections.abc import Awaitable, Callable
from functools import partial
from http import HTTPStatus
from typing import Any

import httpx
import pytest
import respx

from bankid_sdk import AsyncV60
from bankid_sdk.errors import (
    AlreadyInProgress,
    InternalServerError,
    InvalidParameters,
    MethodNotAllowed,
    NotFound,
    RequestTimeout,
    ServiceUnavailable,
    Unauthorized,
    UnknownError,
    UnsupportedMediaType,
)
from tests.mocks import bankid_mock


@pytest.fixture()
def default_routing(
    request: pytest.FixtureRequest,
    async_v60: AsyncV60,
) -> tuple[respx.Route, Callable[[], Awaitable[Any]]]:
    call: Callable[[], Any]
    if request.param == "auth":
        call = partial(async_v60.auth, end_user_ip="127.0.0.1")
    elif request.param == "sign":
        call = partial(
            async_v60.sign, end_user_ip="127.0.0.1", user_visible_data="visible data"
        )
    elif request.param == "collect":
        call = partial(async_v60.collect, order_ref="ref")
    else:
        assert request.param == "cancel"
        call = partial(async_v60.cancel, order_ref="ref")

    return bankid_mock[request.param], call


@pytest.mark.parametrize(
    ("status", "error_code", "expected_exc"),
    [
        pytest.param(
            HTTPStatus.BAD_REQUEST,
            "alreadyInProgress",
            AlreadyInProgress,
            id="already_in_progress_on_alreadyInProgress_error_code",
        ),
        pytest.param(
            HTTPStatus.BAD_REQUEST,
            "invalidParameters",
            InvalidParameters,
            id="invalid_parameters_on_invalidParameters_error_code",
        ),
        pytest.param(
            HTTPStatus.UNAUTHORIZED,
            "unauthorized",
            Unauthorized,
            id="unauthorized_on_unauthorized_error_code_and_status",
        ),
        pytest.param(
            HTTPStatus.FORBIDDEN,
            "unauthorized",
            Unauthorized,
            id="unauthorized_on_unauthorized_error_code_and_forbidden_status",
        ),
        pytest.param(
            HTTPStatus.NOT_FOUND,
            "notFound",
            NotFound,
            id="not_found_on_notFound_error_code",
        ),
        pytest.param(
            HTTPStatus.METHOD_NOT_ALLOWED,
            "methodNotAllowed",
            MethodNotAllowed,
            id="method_not_allowed_on_methodNotAllowed_error_code",
        ),
        pytest.param(
            HTTPStatus.REQUEST_TIMEOUT,
            "requestTimeout",
            RequestTimeout,
            id="request_timeout_on_requestTimeout_error_code",
        ),
        pytest.param(
            HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            "unsupportedMediaType",
            UnsupportedMediaType,
            id="unsupported_media_type_on_unsupportedMediaType_error_code",
        ),
        pytest.param(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "internalError",
            InternalServerError,
            id="internal_server_error_on_internalError_error_code",
        ),
        pytest.param(
            HTTPStatus.SERVICE_UNAVAILABLE,
            "maintenance",
            ServiceUnavailable,
            id="service_unavailable_on_maintenance_error_code",
        ),
        pytest.param(
            HTTPStatus.BAD_REQUEST,
            "unknown_error_code",
            UnknownError,
            id="unknown_error_on_unknown_error_code",
        ),
        pytest.param(
            HTTPStatus.UNAUTHORIZED,
            "invalidParameters",
            UnknownError,
            id="unknown_error_on_known_code_but_unknown_status",
        ),
    ],
)
@pytest.mark.parametrize(
    "default_routing", ["auth", "sign", "collect", "cancel"], indirect=True
)
async def test_raises(
    default_routing: tuple[respx.Route, Callable[[], Awaitable[Any]]],
    mock_bankid: respx.Router,
    status: HTTPStatus,
    error_code: str,
    expected_exc: type[Exception],
) -> None:
    route, call = default_routing
    route.return_value = httpx.Response(
        status, json={"errorCode": error_code, "details": "details"}
    )
    with pytest.raises(expected_exc):
        await call()
