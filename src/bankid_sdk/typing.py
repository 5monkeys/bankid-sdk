from typing import NewType, final


@final
class TransactionID(str):
    __slots__ = ()


OrderRef = NewType("OrderRef", str)
Base64 = NewType("Base64", str)
PersonalNumber = NewType("PersonalNumber", str)
