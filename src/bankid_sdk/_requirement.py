from __future__ import annotations

from dataclasses import dataclass
from typing import (
    Any,
    Literal,
)

from .typing import PersonalNumber


def validate_personal_number(value: str | None, /) -> PersonalNumber | None:
    """
    Naive validation of a (swedish) personal number format
    """
    if value is None:
        return None

    # TODO: Support length 10 also?
    personal_number_length = 12
    if len(value) != personal_number_length:
        raise ValueError("Personal number not of length 12")
    if not value.isdigit():
        raise ValueError("Personal number includes non digits")

    return PersonalNumber(value)


@dataclass()
class Requirement:
    pin_code: Literal[True] | None = None
    mrtd: Literal[True] | None = None
    card_reader: Literal["class1", "class2"] | None = None
    certificate_policies: list[str] | None = None
    personal_number: str | None = None


def _build_requirement_data(
    _requirement: Requirement | None, /
) -> dict[str, Any] | None:
    requirement = {}
    if _requirement is not None:
        for req_key, req in [
            ("pinCode", _requirement.pin_code),
            ("mrtd", _requirement.mrtd),
            ("cardReader", _requirement.card_reader),
            ("certificatePolicies", _requirement.certificate_policies),
            ("personalNumber", validate_personal_number(_requirement.personal_number)),
        ]:
            if req is not None:
                requirement[req_key] = req
    return requirement or None
