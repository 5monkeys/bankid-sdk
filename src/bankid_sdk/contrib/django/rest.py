from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from http import HTTPStatus
from typing import Any

import httpx
from django.conf import settings as django_settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from typing_extensions import TypeAlias

import bankid_sdk
from bankid_sdk.typing import TransactionID
from bankid_sdk.utils import logger

from .request import get_client_ip, parse_json_body, require_POST
from .transaction import envelop, mask_last_four, verify_envelope

View: TypeAlias = Callable[[HttpRequest], HttpResponse]
APIView: TypeAlias = Callable[[HttpRequest, dict[str, Any]], HttpResponse]


def exception_handler(view: View) -> View:
    @wraps(view)
    def inner(request: HttpRequest) -> HttpResponse:
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


def api_view(view: APIView) -> View:
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
        base_url=bankid_sdk.config.API_BASE_URL, cert=bankid_sdk.config.CERT
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


def validate_transaction_id(
    view: Callable[[HttpRequest, TransactionID], HttpResponse]
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
def check(request: HttpRequest, transaction_id: TransactionID) -> JsonResponse:
    with httpx.Client(
        base_url=bankid_sdk.config.API_BASE_URL, cert=bankid_sdk.config.CERT
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
def cancel(request: HttpRequest, transaction_id: TransactionID) -> HttpResponse:
    with httpx.Client(
        base_url=bankid_sdk.config.API_BASE_URL, cert=bankid_sdk.config.CERT
    ) as client:
        bankid_sdk.cancel(bankid_sdk.SyncV60(client=client), transaction_id)

    return HttpResponse(status=HTTPStatus.NO_CONTENT, content_type="application/json")
