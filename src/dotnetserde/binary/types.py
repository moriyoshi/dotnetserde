import datetime
import typing

from .models import (
    ArrayInfo,
    ClassTypeInfo,
    MemberInfo,
    PrimitiveType,
    PrimitiveTypeUnion,
    TypeInfo,
)


class DeserializationContext(typing.Protocol):
    def set_header(self, root_id: int, header_id: int, major_version: int, minor_version: int) -> None:
        ...  # pragma: nocover

    def add_library_id_name_mapping(self, id_: int, name: str) -> None:
        ...  # pragma: nocover

    def library_id_resolvable(self, id_: int) -> bool:
        ...  # pragma: nocover

    def add_object(self, id_: int, instance: typing.Any) -> None:
        ...  # pragma: nocover

    def fetch_object(self, id_: int) -> typing.Any:
        ...  # pragma: nocover


class LengthPrefixedStringReader(typing.Protocol):
    def __call__(self, f: typing.BinaryIO) -> str:
        ...  # pragma: nocover


class ClassInfoReader(typing.Protocol):
    def __call__(self, f: typing.BinaryIO) -> typing.Tuple[int, str, typing.Sequence[str]]:
        ...  # pragma: nocover


class ClassTypeInfoReader(typing.Protocol):
    def __call__(self, ctx: DeserializationContext, f: typing.BinaryIO) -> ClassTypeInfo:
        ...  # pragma: nocover


class MemberTypeInfoReader(typing.Protocol):
    def __call__(
        self, ctx: DeserializationContext, member_names: typing.Collection[str], f: typing.BinaryIO
    ) -> typing.Iterable[MemberInfo]:
        ...  # pragma: nocover


class Deserializer(typing.Protocol):
    code_to_handler_map: typing.Mapping[int, typing.Callable[[DeserializationContext, typing.BinaryIO], bool]]

    def __call__(self, f: typing.BinaryIO) -> typing.Any:
        ...  # pragma: nocover


TypeInfoAndCardinality = typing.Tuple[TypeInfo, int]


class ElementValueReader(typing.Protocol):
    def __call__(
        self,
        ctx: DeserializationContext,
        elements: typing.Iterable[TypeInfoAndCardinality],
        f: typing.BinaryIO,
    ) -> typing.Iterable[typing.Any]:
        ...  # pragma: nocover


class UntypedPrimitiveValueReader(typing.Protocol):
    def __call__(
        self, primitive_type: PrimitiveType, f: typing.BinaryIO
    ) -> typing.Iterator[PrimitiveTypeUnion]:
        ...  # pragma: nocover


class ArrayInfoReader(typing.Protocol):
    def __call__(self, f: typing.BinaryIO) -> ArrayInfo:
        ...  # pragma: nocover


class RecordHandler(typing.Protocol):
    CODE: int

    def deserialize(
        self, ctx: DeserializationContext, f: typing.BinaryIO
    ) -> typing.Tuple[typing.Optional[typing.Iterator[typing.Any]], bool]:
        ...  # pragma: nocover


class RecordHandlerFactoryArgs(typing.TypedDict):
    length_prefixed_string_reader: LengthPrefixedStringReader
    class_info_reader: ClassInfoReader
    class_type_info_reader: ClassTypeInfoReader
    member_type_info_reader: MemberTypeInfoReader
    untyped_primitive_value_reader: UntypedPrimitiveValueReader
    element_value_reader: ElementValueReader
    array_info_reader: ArrayInfoReader
    member_record_handlers: typing.Mapping[int, RecordHandler]


class RecordHandlerFactory(typing.Protocol):
    def __call__(self, **kwargs) -> RecordHandler:
        ...  # pragma: nocover


class TimezoneLocalizer(typing.Protocol):
    def __call__(self, dt: datetime.datetime) -> datetime.datetime:
        ...  # pragma: nocover


class DeserializationResult(typing.Protocol):
    root_id: typing.Optional[int]
    header_id: typing.Optional[int]
    major_version: typing.Optional[int]
    minor_version: typing.Optional[int]
    library_id_name_mappings: typing.Dict[int, str]
    objects: typing.Dict[int, typing.Any]
