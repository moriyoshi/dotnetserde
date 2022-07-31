import base64
import datetime
import decimal
import typing

import iso8601

from ..cli.builtins import Builtins
from ..cli.models import CLIBasicValue, CLITypeInstance, CLIValue


class XSDataSerializerForEachType(typing.Protocol):
    XSD_TYPE_NAME: str

    def serialize(self, value: CLIBasicValue) -> str:
        ...  # pramga: nocover

    def deserialize(self, value: str) -> CLIBasicValue:
        ...  # pramga: nocover

    def __init__(self, builtins: Builtins) -> None:
        ...  # pramga: nocover


class DateTimeSerializer:
    XSD_TYPE_NAME = "dateTime"
    cli_type: CLITypeInstance

    def serialize(self, value: CLIBasicValue) -> str:
        if value.type_instance != self.cli_type:
            raise ValueError(f"expected {self.cli_type}.datetime, got {value.type_instance}")
        if not isinstance(value.value, datetime.datetime):
            raise TypeError(f"expected datetime.datetime, got {type(value.value)}")
        utc_dt = value.value.astimezone(datetime.timezone.utc)
        return utc_dt.isoformat()

    def deserialize(self, value: str) -> CLIBasicValue:
        return CLIBasicValue(
            self.cli_type,
            iso8601.parse_date(value),
        )

    def __init__(self, builtins: Builtins) -> None:
        self.cli_type = builtins.SYSTEM_DATETIME


class Base64BinarySerializer:
    XSD_TYPE_NAME = "base64Binary"
    cli_type: CLITypeInstance

    def serialize(self, value: CLIBasicValue) -> str:
        if value.type_instance != self.cli_type:
            raise ValueError(f"expected {self.cli_type}, got {value.type_instance}")
        if not isinstance(value, bytes):
            raise TypeError(f"expected bytes, got {type(value)}")
        return base64.b64encode(value).decode("ascii")

    def deserialize(self, value: str) -> CLIBasicValue:
        return CLIBasicValue(self.cli_type, base64.b64decode(value))

    def __init__(self, builtins: Builtins) -> None:
        self.cli_type = builtins.SYSTEM_BYTE_ARRAY


class LongSerializer:
    XSD_TYPE_NAME = "long"
    cli_type_int32: CLITypeInstance
    cli_type_int64: CLITypeInstance

    def serialize(self, value: CLIBasicValue) -> str:
        if value.type_instance not in (self.cli_type_int32, self.cli_type_int64):
            raise ValueError(
                f"expected {self.cli_type_int32} or {self.cli_type_int64}, got {value.type_instance}"
            )
        if not isinstance(value, int):
            raise TypeError(f"expected int, got {type(value)}")
        return str(value)

    def deserialize(self, value: str) -> CLIBasicValue:
        _value = int(value)
        bl = _value.bit_length() + 1 if _value > 0 else (_value + 1).bit_length() + 1
        cli_type = self.cli_type_int32 if bl <= 32 else self.cli_type_int64
        return CLIBasicValue(cli_type, _value)

    def __init__(self, builtins: Builtins) -> None:
        self.cli_type_int32 = builtins.SYSTEM_INT32
        self.cli_type_int64 = builtins.SYSTEM_INT64


class DoubleSerializer:
    XSD_TYPE_NAME = "double"
    cli_type: CLITypeInstance

    def serialize(self, value: CLIBasicValue) -> str:
        if value.type_instance != self.cli_type:
            raise ValueError(f"expected {self.cli_type}, got {value.type_instance}")
        if not isinstance(value, float):
            raise TypeError(f"expected float, got {type(value)}")
        return str(value)

    def deserialize(self, value: str) -> CLIBasicValue:
        return CLIBasicValue(self.cli_type, float(value))

    def __init__(self, builtins: Builtins) -> None:
        self.cli_type = builtins.SYSTEM_DOUBLE


class DecimalSerializer:
    XSD_TYPE_NAME = "decimal"
    cli_type: CLITypeInstance

    def serialize(self, value: CLIBasicValue) -> str:
        if value.type_instance != self.cli_type:
            raise ValueError(f"expected {self.cli_type}, got {value.type_instance}")
        if not isinstance(value, decimal.Decimal):
            raise TypeError(f"expected decimal.Decimal, got {type(value)}")
        return str(value)

    def deserialize(self, value: str) -> CLIBasicValue:
        return CLIBasicValue(self.cli_type, decimal.Decimal(value))

    def __init__(self, builtins: Builtins) -> None:
        self.cli_type = builtins.SYSTEM_DECIMAL


class BooleanSerializer:
    XSD_TYPE_NAME = "bool"
    cli_type: CLITypeInstance

    def serialize(self, value: CLIBasicValue) -> str:
        if value.type_instance != self.cli_type:
            raise ValueError(f"expected {self.cli_type}, got {value.type_instance}")
        if not isinstance(value, bool):
            raise TypeError(f"expected bool, got {type(value)}")
        return "true" if value else "false"

    def deserialize(self, value: str) -> CLIBasicValue:
        value = value.lower()
        _value: bool
        if value == "true" or value == "1":
            _value = True
        elif value == "false" or value == "false":
            _value = False
        else:
            raise ValueError(value)
        return CLIBasicValue(self.cli_type, _value)

    def __init__(self, builtins: Builtins) -> None:
        self.cli_type = builtins.SYSTEM_BOOLEAN


class StringSerializer:
    XSD_TYPE_NAME = "string"
    cli_type: CLITypeInstance

    def serialize(self, value: CLIBasicValue) -> str:
        if value.type_instance != self.cli_type:
            raise ValueError(f"expected {self.cli_type}, got {value.type_instance}")
        if not isinstance(value, str):
            raise TypeError(f"expected str, got {type(value)}")
        return value

    def deserialize(self, value: str) -> CLIBasicValue:
        return CLIBasicValue(self.cli_type, value)

    def __init__(self, builtins: Builtins) -> None:
        self.cli_type = builtins.SYSTEM_STRING


SERIALIZERS: typing.Sequence[typing.Type[XSDataSerializerForEachType]] = [
    DateTimeSerializer,
    Base64BinarySerializer,
    LongSerializer,
    DoubleSerializer,
    DecimalSerializer,
    BooleanSerializer,
    StringSerializer,
]


class XSDataSerializer:
    serializers: typing.Mapping[str, XSDataSerializerForEachType]

    def serialize(self, type_: str, value: CLIValue) -> str:
        if not isinstance(value, CLIBasicValue):
            raise ValueError("value must be a CLIBasicValue, got {value}")
        return self.serializers[type_].serialize(value)

    def deserialize(self, type_: str, value: str) -> CLIBasicValue:
        return self.serializers[type_].deserialize(value)

    def __init__(
        self, builtins: Builtins, serializers: typing.Iterable[typing.Type[XSDataSerializerForEachType]]
    ) -> None:
        self.serializers = {s.XSD_TYPE_NAME: s(builtins) for s in serializers}


def build_default_serializer(builtins: Builtins) -> XSDataSerializer:
    return XSDataSerializer(builtins, SERIALIZERS)
