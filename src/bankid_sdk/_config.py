from __future__ import annotations

from collections.abc import Iterable, Mapping
from contextlib import suppress
from types import MappingProxyType
from typing import (
    TYPE_CHECKING,
    Any,
    Final,
    Generic,
    Literal,
    TypeVar,
    Union,
    overload,
)

from typing_extensions import Self, TypeAlias

from ._actions import (
    Action,
    AsyncAction,
    AsyncAuthAction,
    AsyncSignAction,
    AuthAction,
    SignAction,
)

if TYPE_CHECKING:
    from ._storage import Storage


class ConfigurationError(Exception):
    ...


T = TypeVar("T")
_NOT_SET: Final = object()


class LazyAttr(Generic[T]):
    """
    A type that allows for lazily loaded configuration values. A kind of syntactic sugar
    for declaring a property with getter and setter.

    Allows a container instance to exist but hold no attribute value until later on.
    """

    __slots__ = ("value", "attrname")
    value: T
    attrname: str | None

    def __init__(self) -> None:
        self.attrname = None

    def __set_name__(self, owner: Any, name: str) -> None:
        if self.attrname is None:
            self.attrname = name
        elif name != self.attrname:
            raise TypeError(
                "Cannot assign the same LazyAttr to two different names "
                f"({self.attrname!r} and {name!r})"
            )

    @overload
    def __get__(self, instance: None, owner: Any = ...) -> Self:
        ...

    @overload
    def __get__(self, instance: _Configuration, owner: Any = ...) -> T:
        ...

    def __get__(self, instance: _Configuration | None, owner: Any = None) -> Self | T:
        if instance is None:
            return self

        if getattr(self, "value", _NOT_SET) is _NOT_SET:
            raise ConfigurationError(f"No value configured for {self.attrname}")

        return self.value

    def __set__(self, instance: _Configuration, value: T) -> None:
        self.value = value

    def reset(self) -> None:
        with suppress(AttributeError):
            del self.value


ActionRegistry: TypeAlias = Mapping[
    tuple[Literal["auth", "sign"], str],
    Union[type["Action"], type["AsyncAction"]],
]


class _Configuration:
    API_BASE_URL = LazyAttr[str]()
    STORAGE = LazyAttr["Storage"]()
    # ACTIONS = LazyAttr[Any]()
    ACTIONS = LazyAttr[ActionRegistry]()
    # two-tuple of certificate file path and key file path
    CERT = LazyAttr[tuple[str, str]]()
    # BankID's CA root certificate file
    CA_CERT = LazyAttr[str]()


config: Final = _Configuration()


def configure(
    api_base_url: str | None = None,
    storage: Storage | None = None,
    actions: Iterable[
        type[AuthAction]
        | type[SignAction]
        | type[AsyncAuthAction]
        | type[AsyncSignAction]
    ]
    | None = None,
    certificate: tuple[str, str] | None = None,
    ca_cert: str | None = None,
) -> None:
    if api_base_url is not None:
        config.API_BASE_URL = api_base_url
    if storage is not None:
        config.STORAGE = storage
    if actions is not None:
        config.ACTIONS = MappingProxyType(
            {
                (
                    "auth"
                    if issubclass(action, AuthAction)
                    or issubclass(action, AsyncAuthAction)
                    else "sign",
                    action.name,
                ): action
                for action in actions
            }
        )
    if certificate is not None:
        config.CERT = certificate
    if ca_cert is not None:
        config.CA_CERT = ca_cert
