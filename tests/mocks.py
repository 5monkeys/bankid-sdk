from http import HTTPStatus

import httpx
import respx

bankid_mock = respx.mock(
    base_url="https://example.com/rp/v6.0", assert_all_called=False
)
bankid_mock.post("/auth", name="auth").mock(
    return_value=httpx.Response(HTTPStatus.BAD_REQUEST)
)
bankid_mock.post("/sign", name="sign").mock(
    return_value=httpx.Response(HTTPStatus.BAD_REQUEST)
)
bankid_mock.post("/collect", name="collect").mock(
    return_value=httpx.Response(HTTPStatus.BAD_REQUEST)
)
bankid_mock.post("/cancel", name="cancel").mock(
    return_value=httpx.Response(HTTPStatus.BAD_REQUEST)
)
