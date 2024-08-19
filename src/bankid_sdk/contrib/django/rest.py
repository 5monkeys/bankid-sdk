from __future__ import annotations

import asyncio
import json
from collections.abc import Callable

from bankid_sdk._auth import AuthOrder
from bankid_sdk._collect import CollectResponse
from bankid_sdk._config import config

try:
    from contextlib import aclosing  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def aclosing(thing: Any) -> AsyncGenerator[Any, None]:
        try:
            yield thing
        finally:
            await thing.aclose()


from collections.abc import AsyncGenerator, Awaitable
from functools import wraps
from http import HTTPStatus
from typing import Any, Union

import httpx
from django.conf import settings as django_settings
from django.http import HttpRequest, HttpResponse, JsonResponse, StreamingHttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from typing_extensions import TypeAlias

import bankid_sdk
from bankid_sdk.utils import logger

from .request import get_client_ip, parse_json_body, require_POST
from .transaction import envelop, mask_last_four, verify_envelope

View: TypeAlias = Callable[[HttpRequest], HttpResponse]
APIView: TypeAlias = Callable[..., Union[HttpResponse, Awaitable[HttpResponse]]]

AsyncView: TypeAlias = Callable[..., Union[HttpResponse, Awaitable[HttpResponse]]]


def exception_handler(view: View) -> View:
    @wraps(view)
    def inner(request: HttpRequest) -> Any:
        try:
            return view(request)
        except (bankid_sdk.BankIDAPIError, bankid_sdk.BankIDHTTPError) as exc:
            if isinstance(exc, bankid_sdk.BankIDAPIError):
                logger.error(
                    "apierror http_status=%d error_code=%s", exc.code, exc.error_code
                )
            else:
                logger.warning("httperror")

            retry_after = getattr(django_settings, "BANKID_SDK_DEFAULT_RETRY_AFTER", 1)
            assert retry_after >= 0
            return JsonResponse(
                {"detail": "Service unavailable"},
                status=HTTPStatus.SERVICE_UNAVAILABLE,
                headers={"Retry-After": retry_after},
            )

    return inner


def api_view(view: Any) -> Any:
    return require_POST(
        never_cache(csrf_exempt(exception_handler(parse_json_body(view))))
    )


@api_view
def auth(request: HttpRequest, data: dict[str, Any]) -> JsonResponse:
    action_name = str(data.get("action", ""))
    action = bankid_sdk.config.ACTIONS.get(("auth", action_name))
    if action is None or not issubclass(action, bankid_sdk.AuthAction):
        detail = (
            {"loc": ["action"], "msg": "invalid value", "type": "value_error"}
            if "action" in data
            else {
                "loc": ["action"],
                "msg": "field required",
                "type": "value_error.missing",
            }
        )
        return JsonResponse(
            {"detail": [detail]}, status=HTTPStatus.UNPROCESSABLE_ENTITY
        )

    client_ip = get_client_ip(request)
    if client_ip is None:
        logger.warning("request missing ip")
        return JsonResponse({"detail": "Invalid IP"}, status=HTTPStatus.BAD_REQUEST)

    with httpx.Client(
        base_url=bankid_sdk.config.API_BASE_URL,
        cert=bankid_sdk.config.CERT,
        verify=bankid_sdk.config.CA_CERT,
    ) as client:
        try:
            order = bankid_sdk.init_auth(
                client=bankid_sdk.SyncV60(client=client),
                action=action,
                order_request=bankid_sdk.OrderRequest(
                    end_user_ip=str(client_ip),
                    requirement=None,
                    request=request,
                    context=data.get("context"),
                ),
            )
        except bankid_sdk.InitFailed as exc:
            return JsonResponse(
                {"detail": exc.detail},
                status=(
                    exc.status if exc.status is not None else HTTPStatus.BAD_REQUEST
                ),
            )

    return JsonResponse(
        {
            "transaction_id": envelop(order.transaction_id),
            "auto_start_token": order.auto_start_token,
        }
    )


def async_api_view(view: Any) -> Any:
    return require_POST(never_cache(csrf_exempt(parse_json_body(view))))


@async_api_view
async def async_auth(
    request: HttpRequest, data: dict[str, Any]
) -> StreamingHttpResponse | JsonResponse | None:
    return StreamingHttpResponse(
        _stream_auth_flow(request, data),
        content_type="text/event-stream",
    )


async def _stream_auth_flow(  # noqa: C901
    request: HttpRequest,
    data: dict[str, Any],
) -> AsyncGenerator[str, None]:
    client_ip = get_client_ip(request)
    if client_ip is None:
        logger.warning("request missing ip")
        yield (f"event: failed\ndata: {json.dumps({'detail': 'Invalid IP'})}\n\n")
        return

    async with httpx.AsyncClient(
        base_url=bankid_sdk.config.API_BASE_URL,
        cert=bankid_sdk.config.CERT,
        verify=bankid_sdk.config.CA_CERT,
    ) as client:
        bankid_client = bankid_sdk.AsyncV60(client=client)
        if transaction_id := data.get("transaction_id"):
            transaction_id = verify_envelope(str(transaction_id))
            if transaction := config.STORAGE.load(transaction_id):
                order = AuthOrder(
                    transaction_id=transaction_id,
                    auto_start_token=transaction.order_response.auto_start_token,
                    order_ref=transaction.order_response.order_ref,
                )
            else:
                error_data = json.dumps({"detail": "Invalid transaction"})
                yield f"event: failed\ndata: {error_data}\n\n"
                return
        else:
            action_name = str(data.get("action", ""))
            action = bankid_sdk.config.ACTIONS.get(("auth", action_name))
            if action is None or not issubclass(action, bankid_sdk.AsyncAuthAction):
                error_data = json.dumps({"detail": "Invalid action"})
                yield f"event: failed\ndata: {error_data}\n\n"
                return
            try:
                order = await bankid_sdk.ainit_auth(
                    client=bankid_client,
                    action=action,
                    order_request=bankid_sdk.OrderRequest(
                        end_user_ip=str(client_ip),
                        requirement=None,
                        request=request,
                        context=data.get("context"),
                    ),
                )
            except bankid_sdk.InitFailed as exc:
                yield (f"event: failed\ndata: {json.dumps({'detail': exc.detail})}\n\n")
                return
            except (bankid_sdk.BankIDAPIError, bankid_sdk.BankIDHTTPError):
                yield (
                    f"event: failed\n"
                    f"data: {json.dumps({'detail': 'Service unavailable'})}\n\n"
                )
                return

        json_data = json.dumps(
            {
                "transaction_id": envelop(order.transaction_id),
                "auto_start_token": order.auto_start_token,
            }
        )
        yield f"event: auth\ndata: {json_data}\n\n"

        result: CollectResponse | None = None
        while result is None or isinstance(result, bankid_sdk.PendingCollect):
            try:
                result, qr_code, finalize_data = await bankid_sdk.acheck(
                    bankid_client,
                    order.transaction_id,
                    request,
                )
            except bankid_sdk.FinalizeFailed as exc:
                yield (f"event: failed\ndata: {json.dumps({'detail': exc.detail})}\n\n")
                return

            if isinstance(result, bankid_sdk.PendingCollect):
                json_data = json.dumps(
                    {"hint_code": result.hint_code.value, "qr_code": qr_code}
                )
                yield (f"event: pending\ndata: {json_data}\n\n")
                # Wait for 2 seconds before polling collect again
                await asyncio.sleep(2)
            elif isinstance(result, bankid_sdk.FailedCollect):
                yield (
                    f"event: failed\n"
                    f"data: {json.dumps({'hint_code': result.hint_code.value})}\n\n"
                )
            else:
                assert isinstance(result, bankid_sdk.CompleteCollect)
                order_data = (
                    {
                        "order": {
                            # TODO: "visible_data":
                            #  result.completion_data.user_visible_data,
                            "user": {
                                "name": result.completion_data.user.name,
                                "given_name": result.completion_data.user.given_name,
                                "surname": result.completion_data.user.surname,
                                "personal_number": mask_last_four(
                                    result.completion_data.user.personal_number
                                ),
                            },
                        },
                        "finalize_data": finalize_data,
                    },
                )
                yield (f"event: complete\ndata: {json.dumps(order_data)}\n\n")


def validate_transaction_id(
    view: Callable[[HttpRequest, bankid_sdk.TransactionID], HttpResponse],
) -> Callable[[HttpRequest, dict[str, Any]], HttpResponse]:
    @wraps(view)
    def inner(request: HttpRequest, data: dict[str, Any], /) -> HttpResponse:
        transaction_id = verify_envelope(str(data.get("transaction_id") or ""))
        if transaction_id is None:
            detail = (
                {
                    "loc": ["transaction_id"],
                    "msg": "invalid value",
                    "type": "value_error",
                }
                if "transaction_id" in data
                else {
                    "loc": ["transaction_id"],
                    "msg": "field required",
                    "type": "value_error.missing",
                }
            )
            return JsonResponse(
                {"detail": [detail]}, status=HTTPStatus.UNPROCESSABLE_ENTITY
            )

        try:
            return view(request, transaction_id)
        except bankid_sdk.TransactionExpired:
            return JsonResponse(
                {
                    "detail": [
                        {
                            "loc": ["transaction_id"],
                            "msg": "transaction expired",
                            "type": "value_error.expired",
                        }
                    ]
                },
                status=HTTPStatus.UNPROCESSABLE_ENTITY,
            )

    return inner


@api_view
@validate_transaction_id
def check(
    request: HttpRequest, transaction_id: bankid_sdk.TransactionID
) -> JsonResponse:
    with httpx.Client(
        base_url=bankid_sdk.config.API_BASE_URL,
        cert=bankid_sdk.config.CERT,
        verify=bankid_sdk.config.CA_CERT,
    ) as client:
        try:
            result, qr_code = bankid_sdk.check(
                bankid_sdk.SyncV60(client=client), transaction_id, request
            )
        except bankid_sdk.FinalizeFailed as exc:
            return JsonResponse(
                {"detail": exc.detail},
                status=(
                    exc.status if exc.status is not None else HTTPStatus.BAD_REQUEST
                ),
            )

    response_data: dict[str, Any]
    if isinstance(result, bankid_sdk.PendingCollect):
        response_data = {
            "status": "pending",
            "hint_code": result.hint_code.value,
        }
        if qr_code is not None:
            response_data["qr_code"] = qr_code
    elif isinstance(result, bankid_sdk.FailedCollect):
        response_data = {
            "status": "failed",
            "hint_code": result.hint_code.value,
        }
    else:
        assert isinstance(result, bankid_sdk.CompleteCollect)
        response_data = {
            "status": "complete",
            "order": {
                # TODO: "visible_data": result.completion_data.user_visible_data,
                "user": {
                    "name": result.completion_data.user.name,
                    "given_name": result.completion_data.user.given_name,
                    "surname": result.completion_data.user.surname,
                    "personal_number": mask_last_four(
                        result.completion_data.user.personal_number
                    ),
                },
            },
        }

    return JsonResponse(response_data)


@api_view
@validate_transaction_id
def cancel(
    request: HttpRequest, transaction_id: bankid_sdk.TransactionID
) -> HttpResponse:
    with httpx.Client(
        base_url=bankid_sdk.config.API_BASE_URL,
        cert=bankid_sdk.config.CERT,
        verify=bankid_sdk.config.CA_CERT,
    ) as client:
        bankid_sdk.cancel(bankid_sdk.SyncV60(client=client), transaction_id)

    return HttpResponse(status=HTTPStatus.NO_CONTENT, content_type="application/json")
