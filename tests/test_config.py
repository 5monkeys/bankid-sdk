import sys

import pytest

import bankid_sdk
from bankid_sdk._config import ConfigurationError, LazyAttr


@pytest.fixture()
def _reset_config() -> None:
    for value in bankid_sdk.config.__class__.__dict__.values():
        if isinstance(value, LazyAttr):
            value.reset()


class TestLazyAttr:
    def test_raises_runtimeerror_when_assigning_same_instance_to_different_names(
        self,
    ) -> None:
        exc = TypeError if sys.version_info >= (3, 12) else RuntimeError
        x = LazyAttr[int]()
        with pytest.raises(exc):

            class Obj:
                A = x
                B = x

    def test_can_reuse_instance_on_multiple_declarations_under_the_same_name(
        self,
    ) -> None:
        x = LazyAttr[int]()

        class Obj1:
            A = x

        class Obj2:
            A = x

        assert Obj1.A is Obj2.A


class TestConfigure:
    @pytest.mark.usefixtures("_reset_config")
    def test_raises_configuration_error_for_unset_value(self) -> None:
        bankid_sdk.configure()
        with pytest.raises(ConfigurationError, match=r"API_BASE_URL"):
            _ = bankid_sdk.config.API_BASE_URL
