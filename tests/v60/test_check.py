from datetime import date
from http import HTTPStatus

import httpx
import pytest

import bankid_sdk
from tests.mocks import bankid_mock

pytestmark = pytest.mark.usefixtures("mock_bankid")


@pytest.mark.xfail(
    reason="Support BankID's custom _date_ format Z suffix", raises=AssertionError
)
def test_supports_bankid_responding_with_Z_as_timezone_suffix(
    sync_v60: bankid_sdk.SyncV60,
) -> None:
    bankid_mock["collect"].return_value = httpx.Response(
        HTTPStatus.OK,
        json={
            "orderRef": "ref",
            "status": "complete",
            "completionData": {
                "user": {
                    "personalNumber": "190000000000",
                    "name": "John Smith",
                    "givenName": "John",
                    "surname": "Smith",
                },
                "device": {"ipAddress": "127.0.0.1"},
                "bankIdIssueDate": "2023-11-29Z",
                "signature": "base64",
                "ocspResponse": "base64",
            },
        },
    )
    response = sync_v60.collect(bankid_sdk.OrderRef("ref"))
    assert isinstance(response, bankid_sdk.CompleteCollect)
    assert response.completion_data.bankid_issue_date == date(2023, 11, 29)
