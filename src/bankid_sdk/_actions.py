from __future__ import annotations

from abc import ABC, abstractmethod
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Literal,
    NamedTuple,
)

from abcattrs import Abstract, abstractattrs

if TYPE_CHECKING:
    from ._collect import CompleteCollect


class UserAuthData(NamedTuple):
    visible: str | None
    non_visible: str | None
    visible_format: Literal["simpleMarkdownV1"] | None


class UserSignData(NamedTuple):
    visible: str
    non_visible: str | None
    visible_format: Literal["simpleMarkdownV1"] | None


class InitFailed(Exception):
    """
    Exception that can be raised to signal that action initialisation failed
    """

    def __init__(self, *, detail: str | None = None, status: int | None = None) -> None:
        self.detail = detail if detail is not None else "Initialisation failed"
        self.status = status
        super().__init__(detail)


class FinalizeFailed(Exception):
    """
    Exception that can be raised to signal that action finalization failed
    """

    def __init__(self, *, detail: str | None = None, status: int | None = None) -> None:
        self.detail = detail if detail is not None else "Completion failed"
        self.status = status
        super().__init__(detail)


TransactionContext = Any


@abstractattrs
class Action(ABC):
    name: ClassVar[Abstract[str]]

    @abstractmethod
    def initialize(
        self, request: Any, context: Any
    ) -> (
        tuple[UserAuthData, TransactionContext]
        | tuple[UserSignData, TransactionContext]
    ):
        """
        Returned transaction context from init is passed as input to finalize
        """
        ...

    @abstractmethod
    def finalize(
        self,
        response: CompleteCollect,
        request: Any,
        context: TransactionContext,
    ) -> None: ...


class AuthAction(Action):
    @abstractmethod
    def initialize(
        self, request: Any, context: Any
    ) -> tuple[UserAuthData, TransactionContext]:
        """
        Returned transaction context from init is passed as input to finalize
        """
        ...


class SignAction(Action):
    @abstractmethod
    def initialize(
        self, request: Any, context: Any
    ) -> tuple[UserSignData, TransactionContext]:
        """
        Returned transaction context from init is passed as input to finalize
        """
        ...
