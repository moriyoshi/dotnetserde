import dataclasses
import datetime
import decimal
import enum
import typing


class BinaryType(enum.IntEnum):
    PRIMITIVE = 0
    STRING = 1
    OBJECT = 2
    SYSTEM_CLASS = 3
    CLASS = 4
    OBJECT_ARRAY = 5
    STRING_ARRAY = 6
    PRIMITIVE_ARRAY = 7


class PrimitiveType(enum.IntEnum):
    BOOLEAN = 1
    BYTE = 2
    CHAR = 3
    DECIMAL = 5
    DOUBLE = 6
    INT16 = 7
    INT32 = 8
    INT64 = 9
    SBYTE = 10
    SINGLE = 11
    TIMESPAN = 12
    DATETIME = 13
    UINT16 = 14
    UINT32 = 15
    UINT64 = 16
    NULL = 17
    STRING = 18


PrimitiveTypeUnion = typing.Union[
    int,
    float,
    decimal.Decimal,
    datetime.timedelta,
    datetime.datetime,
    str,
    None,
]


class BinaryArrayType(enum.IntEnum):
    SINGLE = 0
    JAGGED = 1
    RECTANGULAR = 2
    SINGLE_OFFSET = 3
    JAGGED_OFFSET = 4
    RECTANGULAR_OFFSET = 5


@dataclasses.dataclass
class ClassTypeInfo:
    name: str
    library_id: int


@dataclasses.dataclass
class TypeInfo:
    binary_type: BinaryType
    additional_info: typing.Union[PrimitiveType, ClassTypeInfo, str, None]


@dataclasses.dataclass
class MemberInfo:
    name: str
    type_info: TypeInfo


@dataclasses.dataclass
class ClassInfo:
    object_id: int
    name: str
    members: typing.Collection[MemberInfo] = dataclasses.field(default_factory=list)
    library_id: typing.Optional[int] = None


@dataclasses.dataclass
class ArrayInfo:
    object_id: int
    shape: typing.Sequence[int]
    lower_bounds: typing.Sequence[int]
    type: typing.Optional[BinaryArrayType] = None
    type_info: typing.Optional[TypeInfo] = None


@dataclasses.dataclass
class ObjectReference:
    object_id: int


@dataclasses.dataclass
class Instance:
    class_info: ClassInfo
    values: typing.Optional[typing.Sequence[typing.Any]] = None


@dataclasses.dataclass
class Array:
    array_info: ArrayInfo
    values: typing.Optional[typing.Sequence[typing.Any]] = None


@dataclasses.dataclass(frozen=True, eq=True)
class LibraryInfo:
    name: str
    version: str
    culture: str
    public_key_token: typing.Optional[str]
