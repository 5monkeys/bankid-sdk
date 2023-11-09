import asyncio
from collections import deque
from collections.abc import Awaitable, Callable, Generator, Iterable
from contextlib import AbstractContextManager, ExitStack, contextmanager
from functools import wraps
from typing import (
    Any,
    Concatenate,
    Final,
    Literal,
    ParamSpec,
    Protocol,
    TypeVar,
    overload,
)
from urllib.parse import urljoin

import httpx

from ._auth import build_auth_request
from ._collect import (
    CompleteCollect,
    FailedCollect,
    PendingCollect,
    process_collect_response,
)
from ._order import OrderResponse, process_order_response
from ._requirement import Requirement
from ._sign import build_sign_request
from .errors import httpx_error_hook
from .typing import OrderRef


class GetExcHooks(Protocol):
    def get_exc_hooks(self) -> Iterable[AbstractContextManager[Any]]:
        ...


@contextmanager
def context_bundle(
    managers: Iterable[AbstractContextManager[Any]], /
) -> Generator[ExitStack, None, None]:
    """
    Bundles given context managers to a single one. Contexts are activated in passed
    in order.
    """
    with ExitStack() as stack:
        for manager in managers:
            stack.enter_context(manager)
        yield stack


P = ParamSpec("P")
T = TypeVar("T")
_Client = TypeVar("_Client", bound=GetExcHooks)


@overload
def handle_exception(
    method: Callable[Concatenate[_Client, P], Awaitable[T]]
) -> Callable[Concatenate[_Client, P], Awaitable[T]]:
    ...


@overload
def handle_exception(
    method: Callable[Concatenate[_Client, P], T]
) -> Callable[Concatenate[_Client, P], T]:
    ...


def handle_exception(
    method: Callable[Concatenate[_Client, P], T]
) -> Callable[Concatenate[_Client, P], Awaitable[T] | T]:
    """
    Activates a client's currently configured exception hook/handling chain.
    """
    if asyncio.iscoroutinefunction(method):

        async def adecorator(self: _Client, /, *args: P.args, **kwargs: P.kwargs) -> T:
            with context_bundle(self.get_exc_hooks()):
                return await method(self, *args, **kwargs)  # type: ignore[no-any-return]

        return adecorator
    else:

        @wraps(method)
        def decorator(self: _Client, /, *args: P.args, **kwargs: P.kwargs) -> T:
            with context_bundle(self.get_exc_hooks()):
                return method(self, *args, **kwargs)

        return decorator


class V60Base:
    __slots__ = ("headers", "_exc_hooks")
    path_prefix: Final[str] = "/rp/v6.0/"

    def __init__(self) -> None:
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self._exc_hooks = deque[AbstractContextManager[Any]]()

    def get_exc_hooks(self) -> Generator[AbstractContextManager[Any], None, None]:
        for _ in range(len(self._exc_hooks)):
            yield self._exc_hooks.popleft()

        # Always keep the default httpx handler as the innermost(first) hook.
        yield httpx_error_hook()

    def build_path(self, component: str) -> str:
        return urljoin(self.path_prefix, component.lstrip("/"))


class AsyncV60(V60Base):
    __slots__ = ("client",)

    def __init__(self, client: httpx.AsyncClient) -> None:
        super().__init__()
        self.client = client

    @handle_exception
    async def auth(
        self,
        end_user_ip: str,
        requirement: Requirement | None = None,
        user_visible_data: str | None = None,
        user_non_visible_data: str | None = None,
        user_visible_data_format: Literal["simpleMarkdownV1"] | None = None,
    ) -> OrderResponse:
        data = build_auth_request(
            end_user_ip,
            requirement,
            user_visible_data,
            user_non_visible_data,
            user_visible_data_format,
        )
        response = await self.client.post(
            self.build_path("/auth"), json=data, headers=self.headers
        )
        return process_order_response(response)

    @handle_exception
    async def sign(
        self,
        end_user_ip: str,
        user_visible_data: str,
        requirement: Requirement | None = None,
        user_non_visible_data: str | None = None,
        user_visible_data_format: Literal["simpleMarkdownV1"] | None = None,
    ) -> OrderResponse:
        data = build_sign_request(
            end_user_ip,
            user_visible_data,
            requirement,
            user_non_visible_data,
            user_visible_data_format,
        )
        response = await self.client.post(
            self.build_path("/sign"), json=data, headers=self.headers
        )
        return process_order_response(response)

    @handle_exception
    async def collect(
        self, order_ref: OrderRef
    ) -> PendingCollect | CompleteCollect | FailedCollect:
        response = await self.client.post(
            self.build_path("/collect"),
            json={"orderRef": order_ref},
            headers=self.headers,
        )
        return process_collect_response(response)

    @handle_exception
    async def cancel(self, order_ref: OrderRef) -> None:
        response = await self.client.post(
            self.build_path("/cancel"),
            json={"orderRef": order_ref},
            headers=self.headers,
        )
        response.raise_for_status()


class SyncV60(V60Base):
    __slots__ = ("client",)

    def __init__(self, client: httpx.Client) -> None:
        super().__init__()
        self.client = client

    @handle_exception
    def auth(
        self,
        end_user_ip: str,
        requirement: Requirement | None = None,
        user_visible_data: str | None = None,
        user_non_visible_data: str | None = None,
        user_visible_data_format: Literal["simpleMarkdownV1"] | None = None,
    ) -> OrderResponse:
        data = build_auth_request(
            end_user_ip,
            requirement,
            user_visible_data,
            user_non_visible_data,
            user_visible_data_format,
        )
        response = self.client.post(
            self.build_path("/auth"), json=data, headers=self.headers
        )
        return process_order_response(response)

    @handle_exception
    def sign(
        self,
        end_user_ip: str,
        user_visible_data: str,
        requirement: Requirement | None = None,
        user_non_visible_data: str | None = None,
        user_visible_data_format: Literal["simpleMarkdownV1"] | None = None,
    ) -> OrderResponse:
        data = build_sign_request(
            end_user_ip,
            user_visible_data,
            requirement,
            user_non_visible_data,
            user_visible_data_format,
        )
        response = self.client.post(
            self.build_path("/sign"), json=data, headers=self.headers
        )
        return process_order_response(response)

    @handle_exception
    def collect(
        self, order_ref: OrderRef
    ) -> PendingCollect | CompleteCollect | FailedCollect:
        response = self.client.post(
            self.build_path("/collect"),
            json={"orderRef": order_ref},
            headers=self.headers,
        )
        return process_collect_response(response)

    @handle_exception
    def cancel(self, order_ref: OrderRef) -> None:
        response = self.client.post(
            self.build_path("/cancel"),
            json={"orderRef": order_ref},
            headers=self.headers,
        )
        response.raise_for_status()
