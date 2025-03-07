from __future__ import annotations

import uuid
from base64 import b64encode
from typing import TYPE_CHECKING, Any, Literal, NamedTuple

from ._actions import AuthAction
from ._config import config
from ._order import OrderRequest, Transaction
from ._requirement import Requirement, _build_requirement_data
from .typing import Base64, TransactionID

if TYPE_CHECKING:
    from ._client import SyncV60


def encode_user_data(value: str | None, /) -> Base64 | None:
    if not value:
        return None

    encoded = b64encode(value.encode())
    length = len(encoded)
    user_data_max_length = 1_500
    if length > user_data_max_length:
        raise ValueError(f"User data too large ({length})")

    return Base64(encoded.decode())


def build_auth_request(
    end_user_ip: str,
    requirement: Requirement | None = None,
    user_visible_data: str | None = None,
    user_non_visible_data: str | None = None,
    user_visible_data_format: Literal["simpleMarkdownV1"] | None = None,
    return_url: str | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {"endUserIp": end_user_ip}
    for key, option in [
        ("requirement", _build_requirement_data(requirement)),
        ("userVisibleData", encode_user_data(user_visible_data)),
        ("userNonVisibleData", encode_user_data(user_non_visible_data)),
        ("userVisibleDataFormat", user_visible_data_format),
        ("returnUrl", return_url),
    ]:
        if option is not None:
            data[key] = option

    return data


class AuthOrder(NamedTuple):
    transaction_id: TransactionID
    auto_start_token: str


def init_auth(
    client: SyncV60, action: type[AuthAction], order_request: OrderRequest
) -> AuthOrder:
    user_data, transaction_context = action().initialize(
        order_request.request, order_request.context
    )
    transaction_id = TransactionID(str(uuid.uuid4()))
    return_url = action().build_return_url(
        order_request.request, transaction_id=transaction_id
    )
    order_response = client.auth(
        end_user_ip=order_request.end_user_ip,
        requirement=order_request.requirement,
        user_visible_data=user_data.visible,
        user_non_visible_data=user_data.non_visible,
        user_visible_data_format=user_data.visible_format,
        return_url=return_url,
    )

    config.STORAGE.save(
        Transaction(
            transaction_id=transaction_id,
            order_response=order_response,
            operation="auth",
            action_name=action.name,
            context=transaction_context,
        )
    )
    return AuthOrder(
        transaction_id=transaction_id,
        auto_start_token=order_response.auto_start_token,
    )
