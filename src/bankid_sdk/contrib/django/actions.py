from collections.abc import Mapping
from types import MappingProxyType
from typing import (
    Literal,
    TypeAlias,
)

from django.conf import settings as django_settings
from django.utils.module_loading import import_string

from bankid_sdk import Action, AuthAction, SignAction

ACTION_KEY: TypeAlias = tuple[Literal["auth", "sign"], str]


# TODO: Move to some default/conveniently declared AppConfig that calls configure..
def load_actions() -> Mapping[ACTION_KEY, type[Action]]:
    operation: Literal["auth", "sign"]
    actions = dict[ACTION_KEY, type[Action]]()
    for action_fullname in django_settings.BANKID_SDK_ACTIONS:
        action_cls = import_string(action_fullname)
        if issubclass(action_cls, AuthAction):
            operation = "auth"
        elif issubclass(action_cls, SignAction):
            operation = "sign"
        # TODO: Register subclass of 'Action' under both sign and auth(?)
        else:
            raise TypeError(
                f"{action_cls.__name__} is not a subclass of AuthAction or SignAction"
            )

        key = (operation, action_cls.name)
        if (collision := actions.get(key)) is not None:
            raise ValueError(
                f"An action for {operation!r} under the name {action_cls.name!r} is"
                f" already registered ({collision.__name__})"
            )

        actions[key] = action_cls

    return MappingProxyType(actions)
