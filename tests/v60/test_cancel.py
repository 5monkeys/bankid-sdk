import json
from collections.abc import Generator
from contextlib import contextmanager
from http import HTTPStatus

import httpx
import pytest
from dirty_equals import Contains

from bankid_sdk import (
    AsyncV60,
    OrderRef,
    SyncV60,
)
from tests.mocks import bankid_mock

pytestmark = pytest.mark.usefixtures("mock_bankid")


@contextmanager
def can_send_cancel_request_context() -> Generator[OrderRef, None, None]:
    bankid_mock["cancel"].return_value = httpx.Response(HTTPStatus.OK, json={})

    yield OrderRef("ref")

    assert bankid_mock["cancel"].call_count == 1
    request = bankid_mock["cancel"].calls.last.request
    assert request.url.path == "/rp/v6.0/cancel"
    assert request.headers.multi_items() == Contains(
        ("accept", "application/json"),
        ("content-type", "application/json"),
    )
    assert json.loads(request.content) == {"orderRef": "ref"}


async def test_can_send_cancel_request_async(async_v60: AsyncV60) -> None:
    with can_send_cancel_request_context() as order_ref:
        await async_v60.cancel(order_ref)


def test_can_send_cancel_request_sync(sync_v60: SyncV60) -> None:
    with can_send_cancel_request_context() as order_ref:
        sync_v60.cancel(order_ref)
