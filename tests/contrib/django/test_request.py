import json
from http import HTTPStatus
from unittest import mock

import pytest
from django.http import JsonResponse, RawPostDataException
from django.test.client import RequestFactory

from bankid_sdk.contrib.django.request import get_client_ip, parse_json_body


class TestParseJSONBody:
    @pytest.mark.parametrize(
        "data",
        [
            pytest.param('{"value": NaN}', id="NaN"),
            pytest.param('{"value": Infinity}', id="Infinity"),
            pytest.param('{"value": -Infinity}', id="-Infinity"),
        ],
    )
    def test_returns_bad_request_when_receiving(self, data: str) -> None:
        view = mock.MagicMock(return_value=JsonResponse({}))
        request = RequestFactory().post("/", data=data, content_type="application/json")
        response = parse_json_body(view)(request)
        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.headers.get("Content-Type") == "application/json"
        assert json.loads(response.content) == {"detail": "Malformed request body"}

        view.assert_not_called()

    def test_returns_raises_error_if_body_is_read_twice(self) -> None:
        # Ensure we don't accidentally read twice by confirming that a
        # RawPostDataException propagates
        view = mock.MagicMock(return_value=JsonResponse({}))
        request = RequestFactory().post("/", data="{}", content_type="application/json")
        request.read()
        with pytest.raises(RawPostDataException):
            parse_json_body(view)(request)

        view.assert_not_called()

    def test_passes_through_empty_body_when_content_length_is_missing(self) -> None:
        view = mock.MagicMock(return_value=JsonResponse({}))
        request = RequestFactory(CONTENT_TYPE="application/json").generic("POST", "/")
        response = parse_json_body(view)(request)
        assert response.status_code == HTTPStatus.OK

        view.assert_called_once_with(request, {})

    def test_passes_through_empty_body_when_content_length_is_zero(self) -> None:
        view = mock.MagicMock(return_value=JsonResponse({}))
        request = RequestFactory(
            CONTENT_TYPE="application/json", CONTENT_LENGTH="0"
        ).generic("POST", "/")
        response = parse_json_body(view)(request)
        assert response.status_code == HTTPStatus.OK

        view.assert_called_once_with(request, {})

    def test_passes_through_empty_body_when_content_length_is_invalid_value(
        self,
    ) -> None:
        view = mock.MagicMock(return_value=JsonResponse({}))
        request = RequestFactory(
            CONTENT_TYPE="application/json", CONTENT_LENGTH="abc"
        ).generic("POST", "/")
        response = parse_json_body(view)(request)
        assert response.status_code == HTTPStatus.OK

        view.assert_called_once_with(request, {})

    def test_returns_unsupported_media_type_on_non_json_contents(self) -> None:
        view = mock.MagicMock(return_value=JsonResponse({}))
        request = RequestFactory().post("/", data="abc", content_type="text/plain")
        response = parse_json_body(view)(request)
        assert response.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
        assert response.headers.get("Content-Type") == "application/json"
        assert json.loads(response.content) == {
            "detail": "Unsupported media type 'text/plain' in request"
        }

        view.assert_not_called()


class TestGetClientIP:
    def test_returns_none_if_remote_addr_is_none(self) -> None:
        request = RequestFactory().get("/", REMOTE_ADDR=None)
        assert get_client_ip(request) is None
