from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, NamedTuple, Protocol, TypedDict

import httpx
from typing_extensions import Self

from ._requirement import Requirement
from .typing import OrderRef


class OrderRequest(NamedTuple):
    end_user_ip: str
    requirement: Requirement | None
    request: Any
    context: Any


@dataclass(frozen=True)
class OrderResponse:
    order_ref: OrderRef
    auto_start_token: str
    qr_start_token: str
    qr_start_secret: str
    start_time: datetime


def process_order_response(response: httpx.Response) -> OrderResponse:
    response.raise_for_status()
    response_data: dict[str, Any] = response.json()
    return OrderResponse(
        order_ref=OrderRef(str(response_data["orderRef"])),
        auto_start_token=str(response_data["autoStartToken"]),
        qr_start_token=str(response_data["qrStartToken"]),
        qr_start_secret=str(response_data["qrStartSecret"]),
        start_time=datetime.now(tz=timezone.utc),
    )


class SerializedTransaction(TypedDict):
    order_ref: OrderRef
    auto_start_token: str
    qr_start_token: str
    qr_start_secret: str
    start_time: str
    operation: Literal["auth", "sign"]
    action_name: str
    context: Any


@dataclass(frozen=True)
class Transaction:
    order_response: OrderResponse
    operation: Literal["auth", "sign"]
    action_name: str
    context: Any

    @classmethod
    def from_dict(cls, obj: dict[str, Any], /) -> Self:
        return cls(
            order_response=OrderResponse(
                order_ref=OrderRef(str(obj["order_ref"])),
                auto_start_token=str(obj["auto_start_token"]),
                qr_start_token=str(obj["qr_start_token"]),
                qr_start_secret=str(obj["qr_start_secret"]),
                start_time=datetime.fromisoformat(obj["start_time"]),
            ),
            operation=str(obj["operation"]),  # type: ignore[arg-type]
            action_name=str(obj["action_name"]),
            context=obj["context"],
        )

    def as_dict(self) -> SerializedTransaction:
        return SerializedTransaction(
            order_ref=self.order_response.order_ref,
            auto_start_token=self.order_response.auto_start_token,
            qr_start_token=self.order_response.qr_start_token,
            qr_start_secret=self.order_response.qr_start_secret,
            start_time=self.order_response.start_time.isoformat(),
            operation=self.operation,
            action_name=self.action_name,
            context=self.context,
        )


class _Order(Protocol):
    @property
    def qr_start_token(self) -> str:
        ...

    @property
    def qr_start_secret(self) -> str:
        ...

    @property
    def start_time(self) -> datetime:
        ...


def generate_qr_code(order: _Order) -> str:
    qr_time = str(
        int(datetime.now(tz=timezone.utc).timestamp() - order.start_time.timestamp())
    )
    return ".".join(
        [
            "bankid",
            order.qr_start_token,
            qr_time,
            hmac.new(
                order.qr_start_secret.encode(), qr_time.encode(), hashlib.sha256
            ).hexdigest(),
        ]
    )
