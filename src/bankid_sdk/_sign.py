from __future__ import annotations

from base64 import b64encode
from collections.abc import Callable
from typing import (
    Any,
    Literal,
)

from ._requirement import Requirement, _build_requirement_data
from .typing import Base64


def _encode_user_data(
    max_length: int, purpose: Literal["visible", "non visible"]
) -> Callable[[str | None], Base64 | None]:
    def validator(value: str | None) -> Base64 | None:
        if not value:
            return None

        encoded = b64encode(value.encode())
        length = len(encoded)
        if length > max_length:
            raise ValueError(f"User {purpose} data too large ({length})")

        return Base64(encoded.decode())

    return validator


def build_sign_request(
    end_user_ip: str,
    user_visible_data: str,
    requirement: Requirement | None = None,
    user_non_visible_data: str | None = None,
    user_visible_data_format: Literal["simpleMarkdownV1"] | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "endUserIp": end_user_ip,
        "userVisibleData": _encode_user_data(40_000, "visible")(user_visible_data),
    }
    for key, option in [
        ("requirement", _build_requirement_data(requirement)),
        (
            "userNonVisibleData",
            _encode_user_data(200_000, "non visible")(user_non_visible_data),
        ),
        ("userVisibleDataFormat", user_visible_data_format),
    ]:
        if option is not None:
            data[key] = option

    return data
