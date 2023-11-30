from __future__ import annotations

import codecs
import io
import json
from collections.abc import Callable
from contextlib import suppress
from functools import wraps
from http import HTTPStatus
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Any, NoReturn

from django.http import HttpRequest, HttpResponse, JsonResponse
from typing_extensions import Concatenate, ParamSpec


def load_stream(request: HttpRequest) -> codecs._ReadableStream:
    # TODO: Return some lazy object to not trigger reading the body in here?
    #       Then rename to 'get_stream'
    return io.BytesIO(request.body)


def strict_constant(obj: str) -> NoReturn:
    raise ValueError(f"Out of range float values are not JSON compliant: {obj!r}")


def parse_json_body(
    view: Callable[[HttpRequest, dict[str, Any]], HttpResponse], /
) -> Callable[[HttpRequest], HttpResponse]:
    @wraps(view)
    def inner(request: HttpRequest) -> HttpResponse:
        meta = request.META
        content_type = meta.get("CONTENT_TYPE", meta.get("HTTP_CONTENT_TYPE")) or ""
        if not content_type.startswith("application/json"):
            return JsonResponse(
                {"detail": f"Unsupported media type {content_type!r} in request"},
                status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            )

        try:
            content_length = int(
                meta.get("CONTENT_LENGTH", meta.get("HTTP_CONTENT_LENGTH", 0))
            )
        except (ValueError, TypeError):
            content_length = 0

        if content_length:
            stream = load_stream(request)
            reader = codecs.getreader("utf-8")
            try:
                decoded_stream = reader(stream)
                data = json.load(decoded_stream, parse_constant=strict_constant)
            except ValueError:
                return JsonResponse(
                    {"detail": "Malformed request body"}, status=HTTPStatus.BAD_REQUEST
                )
        else:
            # No body signalled, play it as an empty dict
            data = {}

        if not isinstance(data, dict):
            # Play any valid JSON, but non dictionary types, as an empty dictionary. In
            # case of validation it could result in an error response. While if the
            # endpoint never looks at the body it's able to produce a success response.
            data = {}

        return view(request, data)

    return inner


def get_client_ip(request: HttpRequest) -> IPv4Address | IPv6Address | None:
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    ip: str | None
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0]
    else:
        ip = request.META.get("REMOTE_ADDR")
        assert ip is None or isinstance(ip, str)

    if ip is not None:
        with suppress(ValueError):
            return ip_address(ip)
    return None


P = ParamSpec("P")


def require_POST(
    view: Callable[Concatenate[HttpRequest, P], HttpResponse]
) -> Callable[Concatenate[HttpRequest, P], HttpResponse]:
    """
    Reimplementation of django.views.decorators.http.require_POST that returns a JSON
    response instead of an HTML response.
    """

    @wraps(view)
    def inner(
        request: HttpRequest, /, *args: P.args, **kwargs: P.kwargs
    ) -> HttpResponse:
        if request.method != "POST":
            if request.method == "HEAD":
                # A HEAD response shouldn't have a body, while one might argue there
                # shouldn't be a content type in that case. In reality it's not worth
                # expecting all clients to handle it.
                return HttpResponse(
                    status=HTTPStatus.METHOD_NOT_ALLOWED,
                    headers={"Allow": "POST", "Content-Type": "text/plain"},
                )

            assert request.method is not None
            return JsonResponse(
                {"detail": f"Method {request.method!r} not allowed"},
                status=HTTPStatus.METHOD_NOT_ALLOWED,
                headers={"Allow": "POST"},
            )
        return view(request, *args, **kwargs)

    return inner
