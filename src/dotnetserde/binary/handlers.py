import datetime
import decimal
import functools
import itertools
import operator
import struct
import typing

from ..utils import collection_move
from .exceptions import (
    InvalidStreamError,
    UnexpectedEOF,
    UnknownRecord,
    UnresolvableLibraryId,
    VersionMismatch,
)
from .models import (
    Array,
    ArrayInfo,
    BinaryArrayType,
    BinaryType,
    ClassInfo,
    ClassTypeInfo,
    Instance,
    ObjectReference,
)
from .types import (
    ArrayInfoReader,
    ClassInfoReader,
    ClassTypeInfoReader,
    DeserializationContext,
    ElementValueReader,
    LengthPrefixedStringReader,
    MemberInfo,
    MemberTypeInfoReader,
    PrimitiveType,
    PrimitiveTypeUnion,
    RecordHandler,
    RecordHandlerFactory,
    RecordHandlerFactoryArgs,
    TimezoneLocalizer,
    TypeInfo,
    TypeInfoAndCardinality,
    UntypedPrimitiveValueReader,
)


def read(f: typing.BinaryIO, n: int) -> bytes:
    b = f.read(n)
    if len(b) < n:
        raise UnexpectedEOF(n, len(b))
    return b


class _LengthPrefixedStringReader:
    def __init__(self, encoding: str) -> None:
        self.encoding = encoding

    def __call__(self, f: typing.BinaryIO) -> str:
        b = read(f, 1)

        l = b[0]
        if l <= 127:
            b = read(f, l)
            return b.decode(self.encoding)

        b = read(f, 1)

        ll = b[0]
        l = (l & 0x7F) | (ll & 0x7F) * 128
        if ll <= 127:
            b = read(f, l)
            return b.decode(self.encoding)

        b = read(f, 1)

        ll = b[0]
        l = (l & 0x7F) | (ll & 0x7F) * 16384
        if ll <= 127:
            b = read(f, l)
            return b.decode(self.encoding)

        b = read(f, 1)

        ll = b[0]
        l = (l & 0x7F) | (ll & 0x7F) * 2097152
        if ll <= 127:
            b = read(f, l)
            return b.decode(self.encoding)

        b = read(f, 1)

        ll = b[0]
        l = (l & 0x7F) | (ll & 0x7F) * 268435456
        if ll <= 127:
            b = read(f, l)
            return b.decode(self.encoding)

        raise InvalidStreamError("invalid length prefix")


class _ClassInfoReader:
    length_prefixed_string_reader: LengthPrefixedStringReader

    def __call__(self, f: typing.BinaryIO) -> typing.Tuple[int, str, typing.Sequence[str]]:
        b = read(f, 4)
        (object_id,) = struct.unpack("<l", b)
        name = self.length_prefixed_string_reader(f)
        b = read(f, 4)
        (member_count,) = struct.unpack("<l", b)
        member_names = [self.length_prefixed_string_reader(f) for _ in range(member_count)]
        return (object_id, name, member_names)

    def __init__(self, length_prefixed_string_reader: LengthPrefixedStringReader) -> None:
        self.length_prefixed_string_reader = length_prefixed_string_reader


class _ClassTypeInfoReader:
    length_prefixed_string_reader: LengthPrefixedStringReader

    def __call__(self, ctx: DeserializationContext, f: typing.BinaryIO) -> ClassTypeInfo:
        typename = self.length_prefixed_string_reader(f)
        b = read(f, 4)
        (library_id,) = struct.unpack("<l", b)
        # if ctx.library_id_resolvable(library_id):
        #     raise UnresolvableLibraryId(library_id)
        return ClassTypeInfo(typename, library_id)

    def __init__(self, length_prefixed_string_reader: LengthPrefixedStringReader) -> None:
        self.length_prefixed_string_reader = length_prefixed_string_reader


class _MemberTypeInfoReader:
    """2.3.1.2 MemberTypeInfo"""

    length_prefixed_string_reader: LengthPrefixedStringReader
    class_type_info_reader: ClassTypeInfoReader

    def read_primitive(self, ctx: DeserializationContext, f: typing.BinaryIO) -> PrimitiveType:
        b = read(f, 1)
        try:
            return PrimitiveType(b[0])
        except ValueError:
            raise InvalidStreamError(f"unknown primitive type: {b[0]}")

    def read_string(self, ctx: DeserializationContext, f: typing.BinaryIO) -> None:
        return None

    def read_object(self, ctx: DeserializationContext, f: typing.BinaryIO) -> None:
        return None

    def read_system_class(self, ctx: DeserializationContext, f: typing.BinaryIO) -> str:
        return self.length_prefixed_string_reader(f)

    def read_class(self, ctx: DeserializationContext, f: typing.BinaryIO) -> ClassTypeInfo:
        return self.class_type_info_reader(ctx, f)  # type: ignore

    def read_object_array(self, ctx: DeserializationContext, f: typing.BinaryIO) -> None:
        return None

    def read_string_array(self, ctx: DeserializationContext, f: typing.BinaryIO) -> None:
        return None

    def read_primitive_array(self, ctx: DeserializationContext, f: typing.BinaryIO) -> PrimitiveType:
        b = read(f, 1)
        try:
            return PrimitiveType(b[0])
        except ValueError:
            raise InvalidStreamError(f"unknown primitive type: {b[0]}")

    additional_info_readers: typing.Mapping[
        BinaryType,
        typing.Callable[
            ["_MemberTypeInfoReader", DeserializationContext, typing.BinaryIO],
            typing.Union[PrimitiveType, ClassTypeInfo, str, None],
        ],
    ] = {
        BinaryType.PRIMITIVE: read_primitive,
        BinaryType.STRING: read_string,
        BinaryType.OBJECT: read_object,
        BinaryType.SYSTEM_CLASS: read_system_class,
        BinaryType.CLASS: read_class,
        BinaryType.OBJECT_ARRAY: read_object_array,
        BinaryType.STRING_ARRAY: read_string_array,
        BinaryType.PRIMITIVE_ARRAY: read_primitive_array,
    }

    def read_additional_info(
        self, ctx: DeserializationContext, binary_type: BinaryType, f: typing.BinaryIO
    ) -> typing.Union[PrimitiveType, ClassTypeInfo, str, None]:
        return self.additional_info_readers[binary_type](self, ctx, f)

    def __call__(
        self, ctx: DeserializationContext, member_names: typing.Collection[str], f: typing.BinaryIO
    ) -> typing.Iterable[MemberInfo]:
        b = read(f, len(member_names))
        if len(b) < len(member_names):
            raise UnexpectedEOF(len(member_names), len(b))

        members: typing.List[MemberInfo] = []
        for name, binary_type_value in zip(member_names, b):
            try:
                binary_type = BinaryType(binary_type_value)
            except ValueError:
                raise InvalidStreamError(f"unknown binary type: {binary_type_value}")
            members.append(
                MemberInfo(
                    name=name,
                    type_info=TypeInfo(
                        binary_type=binary_type,
                        additional_info=self.read_additional_info(ctx, binary_type, f),
                    ),
                )
            )

        return members

    def __init__(
        self,
        length_prefixed_string_reader: LengthPrefixedStringReader,
        class_type_info_reader: ClassTypeInfoReader,
    ) -> None:
        self.length_prefixed_string_reader = length_prefixed_string_reader
        self.class_type_info_reader = class_type_info_reader


class _UntypedPrimitiveValueReader:
    length_prefixed_string_reader: LengthPrefixedStringReader
    timezone_localizer: TimezoneLocalizer

    def read_boolean(self, f: typing.BinaryIO) -> typing.Iterator[bool]:
        b = read(f, 1)
        yield bool(b[0])

    def read_byte(self, f: typing.BinaryIO) -> typing.Iterator[int]:
        b = read(f, 1)
        yield b[0]

    def read_char(self, f: typing.BinaryIO) -> typing.Iterator[int]:
        b = read(f, 2)
        yield int(struct.unpack("<h", b)[0])

    def read_decimal(self, f: typing.BinaryIO) -> typing.Iterator[decimal.Decimal]:
        raise NotImplementedError()

    def read_double(self, f: typing.BinaryIO) -> typing.Iterator[float]:
        b = read(f, 8)
        yield int(struct.unpack("<d", b)[0])

    def read_int16(self, f: typing.BinaryIO) -> typing.Iterator[int]:
        b = read(f, 2)
        yield int(struct.unpack("<h", b)[0])

    def read_int32(self, f: typing.BinaryIO) -> typing.Iterator[int]:
        b = read(f, 4)
        yield int(struct.unpack("<l", b)[0])

    def read_int64(self, f: typing.BinaryIO) -> typing.Iterator[int]:
        b = read(f, 8)
        yield int(struct.unpack("<q", b)[0])

    def read_sbyte(self, f: typing.BinaryIO) -> typing.Iterator[int]:
        b = read(f, 1)
        yield int(struct.unpack("<b", b)[0])

    def read_single(self, f: typing.BinaryIO) -> typing.Iterator[float]:
        b = read(f, 4)
        yield int(struct.unpack("<f", b)[0])

    def read_timespan(self, f: typing.BinaryIO) -> typing.Iterator[datetime.timedelta]:
        b = read(f, 8)
        (time_span,) = struct.unpack("<q", b)
        yield datetime.timedelta(microseconds=time_span / 10.0)

    def read_datetime(self, f: typing.BinaryIO) -> typing.Iterator[datetime.datetime]:
        b = read(f, 8)
        (ticks,) = struct.unpack("<Q", b)
        kind = ticks >> 62
        ticks = ticks & 0x3FFFFFFFFFFFFFFF
        microsecond = (ticks % 10000000) // 10
        ticks //= 10000000
        second = ticks % 60
        ticks //= 60
        minute = ticks % 60
        ticks //= 60
        hour = ticks % 24
        ticks //= 24
        dt = datetime.datetime.combine(
            datetime.date.fromordinal(ticks + 1),
            datetime.time(hour, minute, second, microsecond),
        )

        if kind == 0:
            yield dt
        elif kind == 1:
            yield dt.replace(tzinfo=datetime.timezone.utc)
        elif kind == 2:
            yield self.timezone_localizer(dt)
        else:
            raise InvalidStreamError(f"unknown datetime kind: {kind}")

    def read_uint16(self, f: typing.BinaryIO) -> typing.Iterator[int]:
        b = read(f, 2)
        yield int(struct.unpack("<H", b)[0])

    def read_uint32(self, f: typing.BinaryIO) -> typing.Iterator[int]:
        b = read(f, 4)
        yield int(struct.unpack("<L", b)[0])

    def read_uint64(self, f: typing.BinaryIO) -> typing.Iterator[int]:
        b = read(f, 8)
        yield int(struct.unpack("<Q", b)[0])

    def read_null(self, f: typing.BinaryIO) -> typing.Iterator[None]:
        raise NotImplementedError()

    def read_string(self, f: typing.BinaryIO) -> typing.Iterator[str]:
        yield self.length_prefixed_string_reader(f)

    readers: typing.Mapping[
        PrimitiveType,
        typing.Callable[["_UntypedPrimitiveValueReader", typing.BinaryIO], typing.Iterator[PrimitiveTypeUnion]],
    ] = {
        PrimitiveType.BOOLEAN: read_boolean,
        PrimitiveType.BYTE: read_byte,
        PrimitiveType.CHAR: read_char,
        PrimitiveType.DECIMAL: read_decimal,
        PrimitiveType.DOUBLE: read_double,
        PrimitiveType.INT16: read_int16,
        PrimitiveType.INT32: read_int32,
        PrimitiveType.INT64: read_int64,
        PrimitiveType.SBYTE: read_sbyte,
        PrimitiveType.SINGLE: read_single,
        PrimitiveType.TIMESPAN: read_timespan,
        PrimitiveType.DATETIME: read_datetime,
        PrimitiveType.UINT16: read_uint16,
        PrimitiveType.UINT32: read_uint32,
        PrimitiveType.UINT64: read_uint64,
        PrimitiveType.NULL: read_null,
        PrimitiveType.STRING: read_string,
    }

    def __call__(
        self, primitive_type: PrimitiveType, f: typing.BinaryIO
    ) -> typing.Iterator[PrimitiveTypeUnion]:
        return self.readers[primitive_type](self, f)

    def __init__(
        self,
        length_prefixed_string_reader: LengthPrefixedStringReader,
        timezone_localizer: TimezoneLocalizer,
    ) -> None:
        self.length_prefixed_string_reader = length_prefixed_string_reader
        self.timezone_localizer = timezone_localizer


def read_array_info(f: typing.BinaryIO) -> ArrayInfo:
    b = read(f, 8)
    object_id, length = struct.unpack("<ll", b)
    return ArrayInfo(
        object_id=object_id,
        shape=(length,),
        lower_bounds=(0,),
    )


class SerializedStreamHandler:
    CODE = 0

    def deserialize(
        self, ctx: DeserializationContext, f: typing.BinaryIO
    ) -> typing.Tuple[typing.Optional[typing.Iterator[typing.Any]], bool]:
        b = read(f, 16)
        root_id, header_id, major_version, minor_version = struct.unpack("<llll", b)
        if major_version != 1 and minor_version != 0:
            raise VersionMismatch(
                f"this implementation only supports version 1.0 format; got {major_version}.{minor_version}"
            )
        ctx.set_header(root_id, header_id, major_version, minor_version)
        return None, True

    def __init__(self, **kwargs) -> None:
        pass


class ClassWithIdHandler:
    CODE = 1

    element_value_reader: ElementValueReader

    def deserialize(
        self, ctx: DeserializationContext, f: typing.BinaryIO
    ) -> typing.Tuple[typing.Optional[typing.Iterator[typing.Any]], bool]:
        b = read(f, 8)
        object_id, metadata_id = struct.unpack("<ll", b)
        that_object = ctx.fetch_object(metadata_id)
        assert isinstance(that_object, Instance)
        values = list(
            self.element_value_reader(
                ctx, ((member.type_info, 1) for member in that_object.class_info.members), f
            )
        )
        value = Instance(
            class_info=that_object.class_info,
            values=values,
        )
        ctx.add_object(object_id, that_object)
        return iter((value,)), True

    def __init__(self, **kwargs) -> None:
        _kwargs = typing.cast(RecordHandlerFactoryArgs, kwargs)
        self.element_value_reader = _kwargs["element_value_reader"]


class SystemClassWithMembersHandler:
    CODE = 2

    def deserialize(
        self, ctx: DeserializationContext, f: typing.BinaryIO
    ) -> typing.Tuple[typing.Optional[typing.Iterator[typing.Any]], bool]:
        raise NotImplementedError()

    def __init__(self, **kwargs) -> None:
        pass


class ClassWithMembersHandler:
    CODE = 3

    def deserialize(
        self, ctx: DeserializationContext, f: typing.BinaryIO
    ) -> typing.Tuple[typing.Optional[typing.Iterator[typing.Any]], bool]:
        raise NotImplementedError()

    def __init__(self, **kwargs) -> None:
        pass


class SystemClassWithMembersAndTypesHandler:
    CODE = 4

    class_info_reader: ClassInfoReader
    member_type_info_reader: MemberTypeInfoReader
    element_value_reader: ElementValueReader

    def deserialize(
        self, ctx: DeserializationContext, f: typing.BinaryIO
    ) -> typing.Tuple[typing.Optional[typing.Iterator[typing.Any]], bool]:
        (object_id, name, member_names) = self.class_info_reader(f)
        members = self.member_type_info_reader(ctx, member_names, f)
        class_info = ClassInfo(object_id, name, collection_move(members))
        value = Instance(class_info=class_info)
        ctx.add_object(object_id, value)
        value.values = list(
            self.element_value_reader(ctx, ((member.type_info, 1) for member in class_info.members), f)
        )
        return iter((value,)), True

    def __init__(self, **kwargs) -> None:
        _kwargs = typing.cast(RecordHandlerFactoryArgs, kwargs)
        self.class_info_reader = _kwargs["class_info_reader"]
        self.member_type_info_reader = _kwargs["member_type_info_reader"]
        self.element_value_reader = _kwargs["element_value_reader"]


class ClassWithMembersAndTypesHandler:
    CODE = 5

    class_info_reader: ClassInfoReader
    member_type_info_reader: MemberTypeInfoReader
    element_value_reader: ElementValueReader

    def deserialize(
        self, ctx: DeserializationContext, f: typing.BinaryIO
    ) -> typing.Tuple[typing.Optional[typing.Iterator[typing.Any]], bool]:
        (object_id, name, member_names) = self.class_info_reader(f)
        members = self.member_type_info_reader(ctx, member_names, f)
        b = read(f, 4)
        (library_id,) = struct.unpack("<l", b)
        if not ctx.library_id_resolvable(library_id):
            raise UnresolvableLibraryId(library_id)
        class_info = ClassInfo(object_id, name, collection_move(members), library_id)
        value = Instance(class_info=class_info)
        ctx.add_object(object_id, value)
        value.values = list(
            self.element_value_reader(ctx, ((member.type_info, 1) for member in class_info.members), f)
        )
        return iter((value,)), True

    def __init__(self, **kwargs) -> None:
        _kwargs = typing.cast(RecordHandlerFactoryArgs, kwargs)
        self.class_info_reader = _kwargs["class_info_reader"]
        self.member_type_info_reader = _kwargs["member_type_info_reader"]
        self.element_value_reader = _kwargs["element_value_reader"]


class BinaryObjectStringHandler:
    CODE = 6

    length_prefixed_string_reader: LengthPrefixedStringReader

    def deserialize(
        self, ctx: DeserializationContext, f: typing.BinaryIO
    ) -> typing.Tuple[typing.Optional[typing.Iterator[typing.Any]], bool]:
        b = read(f, 4)
        (object_id,) = struct.unpack("<l", b)
        value = self.length_prefixed_string_reader(f)
        ctx.add_object(object_id, value)
        return iter((value,)), True

    def __init__(self, **kwargs) -> None:
        _kwargs = typing.cast(RecordHandlerFactoryArgs, kwargs)
        self.length_prefixed_string_reader = _kwargs["length_prefixed_string_reader"]


class BinaryArrayHandler:
    CODE = 7

    length_prefixed_string_reader: LengthPrefixedStringReader
    class_type_info_reader: ClassTypeInfoReader
    element_value_reader: ElementValueReader

    def read_primitive(self, ctx: DeserializationContext, f: typing.BinaryIO) -> PrimitiveType:
        b = read(f, 1)
        try:
            return PrimitiveType(b[0])
        except ValueError:
            raise InvalidStreamError(f"unknown primitive type: {b[0]}")

    def read_string(self, ctx: DeserializationContext, f: typing.BinaryIO) -> None:
        return None

    def read_object(self, ctx: DeserializationContext, f: typing.BinaryIO) -> None:
        return None

    def read_system_class(self, ctx: DeserializationContext, f: typing.BinaryIO) -> str:
        return self.length_prefixed_string_reader(f)

    def read_class(self, ctx: DeserializationContext, f: typing.BinaryIO) -> ClassTypeInfo:
        return self.class_type_info_reader(ctx, f)

    def read_object_array(self, ctx: DeserializationContext, f: typing.BinaryIO) -> None:
        return None

    def read_string_array(self, ctx: DeserializationContext, f: typing.BinaryIO) -> None:
        return None

    def read_primitive_array(self, ctx: DeserializationContext, f: typing.BinaryIO) -> PrimitiveType:
        b = read(f, 1)
        try:
            return PrimitiveType(b[0])
        except ValueError:
            raise InvalidStreamError(f"unknown primitive type: {b[0]}")

    additional_info_readers: typing.Mapping[
        BinaryType,
        typing.Callable[
            ["BinaryArrayHandler", DeserializationContext, typing.BinaryIO],
            typing.Union[PrimitiveType, ClassTypeInfo, str, None],
        ],
    ] = {
        BinaryType.PRIMITIVE: read_primitive,
        BinaryType.STRING: read_string,
        BinaryType.OBJECT: read_object,
        BinaryType.SYSTEM_CLASS: read_system_class,
        BinaryType.CLASS: read_class,
        BinaryType.OBJECT_ARRAY: read_object_array,
        BinaryType.STRING_ARRAY: read_string_array,
        BinaryType.PRIMITIVE_ARRAY: read_primitive_array,
    }

    def read_additional_info(
        self, ctx: DeserializationContext, binary_type: BinaryType, f: typing.BinaryIO
    ) -> typing.Union[PrimitiveType, ClassTypeInfo, str, None]:
        return self.additional_info_readers[binary_type](self, ctx, f)

    def deserialize(
        self, ctx: DeserializationContext, f: typing.BinaryIO
    ) -> typing.Tuple[typing.Optional[typing.Iterator[typing.Any]], bool]:
        b = read(f, 9)
        (object_id, binary_array_type_value, rank) = struct.unpack("<lBl", b)
        try:
            binary_array_type = BinaryArrayType(binary_array_type_value)
        except ValueError:
            raise InvalidStreamError(f"unknown binary array type: {binary_array_type_value}")
        if rank < 0:
            raise InvalidStreamError(f"rank must be a non-negative integer, got {rank}")

        lengths: typing.Sequence[int]
        lower_bounds: typing.Sequence[int]

        if binary_array_type in (
            BinaryArrayType.SINGLE_OFFSET,
            BinaryArrayType.JAGGED_OFFSET,
            BinaryArrayType.RECTANGULAR_OFFSET,
        ):
            b = read(f, 4 * rank * 2)
            lengths_and_lower_bounds = struct.unpack(f"<{rank * 2}l", b)
            lengths = lengths_and_lower_bounds[:rank]
            lower_bounds = lengths_and_lower_bounds[rank:]
        else:
            b = read(f, 4 * rank)
            lengths_and_lower_bounds = struct.unpack(f"<{rank}l", b)
            lengths = lengths_and_lower_bounds[:rank]
            lower_bounds = (0,) * rank

        b = read(f, 1)
        try:
            binary_type = BinaryType(b[0])
        except ValueError:
            raise InvalidStreamError(f"unknown binary type: {b[0]}")
        additional_info = self.read_additional_info(ctx, binary_type, f)

        type_info = TypeInfo(
            binary_type,
            additional_info,
        )
        array_info = ArrayInfo(
            object_id,
            lengths,
            lower_bounds,
            binary_array_type,
            type_info=type_info,
        )
        value = Array(array_info=array_info)
        ctx.add_object(object_id, value)
        value.values = list(
            self.element_value_reader(ctx, [(type_info, functools.reduce(operator.mul, lengths))], f)
        )
        return iter((value,)), True

    def __init__(self, **kwargs) -> None:
        _kwargs = typing.cast(RecordHandlerFactoryArgs, kwargs)
        self.length_prefixed_string_reader = _kwargs["length_prefixed_string_reader"]
        self.class_type_info_reader = _kwargs["class_type_info_reader"]
        self.element_value_reader = _kwargs["element_value_reader"]


class MemberPrimitiveTypedHandler:
    CODE = 8

    def deserialize(
        self, ctx: DeserializationContext, f: typing.BinaryIO
    ) -> typing.Tuple[typing.Optional[typing.Iterator[typing.Any]], bool]:
        raise NotImplementedError()

    def __init__(self, **kwargs) -> None:
        pass


class MemberReferenceHandler:
    CODE = 9

    def deserialize(
        self, ctx: DeserializationContext, f: typing.BinaryIO
    ) -> typing.Tuple[typing.Optional[typing.Iterator[typing.Any]], bool]:
        b = read(f, 4)
        (object_id,) = struct.unpack("<l", b)
        return iter((ObjectReference(object_id),)), True

    def __init__(self, **kwargs) -> None:
        pass


class ObjectNullHandler:
    CODE = 10

    def deserialize(
        self, ctx: DeserializationContext, f: typing.BinaryIO
    ) -> typing.Tuple[typing.Optional[typing.Iterator[typing.Any]], bool]:
        return iter((None,)), True

    def __init__(self, **kwargs) -> None:
        pass


class MessageEndHandler:
    CODE = 11

    def deserialize(
        self, ctx: DeserializationContext, f: typing.BinaryIO
    ) -> typing.Tuple[typing.Optional[typing.Iterator[typing.Any]], bool]:
        return None, False

    def __init__(self, **kwargs) -> None:
        pass


class BinaryLibraryHandler:
    CODE = 12

    length_prefixed_string_reader: LengthPrefixedStringReader

    def deserialize(
        self, ctx: DeserializationContext, f: typing.BinaryIO
    ) -> typing.Tuple[typing.Optional[typing.Iterator[typing.Any]], bool]:
        b = read(f, 4)
        (library_id,) = struct.unpack("<l", b)
        library_name = self.length_prefixed_string_reader(f)

        ctx.add_library_id_name_mapping(library_id, library_name)
        return None, True

    def __init__(self, **kwargs) -> None:
        _kwargs = typing.cast(RecordHandlerFactoryArgs, kwargs)
        self.length_prefixed_string_reader = _kwargs["length_prefixed_string_reader"]


class ObjectNullMultiple256Handler:
    CODE = 13

    def deserialize(
        self, ctx: DeserializationContext, f: typing.BinaryIO
    ) -> typing.Tuple[typing.Optional[typing.Iterator[typing.Any]], bool]:
        b = read(f, 1)
        return itertools.repeat(None, b[0]), True

    def __init__(self, **kwargs) -> None:
        pass


class ObjectNullMultipleHandler:
    CODE = 14

    def deserialize(
        self, ctx: DeserializationContext, f: typing.BinaryIO
    ) -> typing.Tuple[typing.Optional[typing.Iterator[typing.Any]], bool]:
        b = read(f, 4)
        (count,) = struct.unpack("<l", b)
        return itertools.repeat(None, count), True

    def __init__(self, **kwargs) -> None:
        pass


class ArraySinglePrimitiveHandler:
    CODE = 15

    array_info_reader: ArrayInfoReader
    element_value_reader: ElementValueReader

    def deserialize(
        self, ctx: DeserializationContext, f: typing.BinaryIO
    ) -> typing.Tuple[typing.Optional[typing.Iterator[typing.Any]], bool]:
        array_info = self.array_info_reader(f)
        b = read(f, 1)
        try:
            primitive_type = PrimitiveType(b[0])
        except ValueError:
            raise InvalidStreamError(f"unknown primitive type: {b[0]}")

        type_info = TypeInfo(
            binary_type=BinaryType.PRIMITIVE,
            additional_info=primitive_type,
        )
        array_info.type_info = type_info
        array_info.type = BinaryArrayType.SINGLE
        value = Array(array_info=array_info)
        ctx.add_object(array_info.object_id, value)
        value.values = list(self.element_value_reader(ctx, [(type_info, array_info.shape[0])], f))
        return iter((value,)), True

    def __init__(self, **kwargs) -> None:
        _kwargs = typing.cast(RecordHandlerFactoryArgs, kwargs)
        self.array_info_reader = _kwargs["array_info_reader"]
        self.element_value_reader = _kwargs["element_value_reader"]


class ArraySingleObjectHandler:
    CODE = 16

    def deserialize(
        self, ctx: DeserializationContext, f: typing.BinaryIO
    ) -> typing.Tuple[typing.Optional[typing.Iterator[typing.Any]], bool]:
        raise NotImplementedError()

    def __init__(self, **kwargs) -> None:
        pass


class ArraySingleStringHandler:
    CODE = 17

    def deserialize(
        self, ctx: DeserializationContext, f: typing.BinaryIO
    ) -> typing.Tuple[typing.Optional[typing.Iterator[typing.Any]], bool]:
        raise NotImplementedError()

    def __init__(self, **kwargs) -> None:
        pass


class MethodCallHandler:
    CODE = 21

    def deserialize(
        self, ctx: DeserializationContext, f: typing.BinaryIO
    ) -> typing.Tuple[typing.Optional[typing.Iterator[typing.Any]], bool]:
        raise NotImplementedError()

    def __init__(self, **kwargs) -> None:
        pass


class MethodReturnHandler:
    CODE = 22

    def deserialize(
        self, ctx: DeserializationContext, f: typing.BinaryIO
    ) -> typing.Tuple[typing.Optional[typing.Iterator[typing.Any]], bool]:
        raise NotImplementedError()

    def __init__(self, **kwargs) -> None:
        pass


class _ElementValueReader:
    length_prefixed_string_reader: LengthPrefixedStringReader
    untyped_primitive_type_reader: UntypedPrimitiveValueReader
    member_record_handlers: typing.Mapping[int, RecordHandler]

    def read_member_reference(
        self, ctx: DeserializationContext, f: typing.BinaryIO
    ) -> typing.Iterator[typing.Any]:
        b = read(f, 1)
        handler = self.member_record_handlers.get(b[0])
        if handler is None:
            raise UnknownRecord(b[0])
        i, continue_ = handler.deserialize(ctx, f)
        assert continue_
        assert i is not None
        return i

    def read_primitive(
        self, ctx: DeserializationContext, type_info: TypeInfo, n: int, f: typing.BinaryIO
    ) -> typing.Iterator[typing.Any]:
        primitive_type = typing.cast(PrimitiveType, type_info.additional_info)
        c = n
        while c > 0:
            elements = list(self.untyped_primitive_type_reader(primitive_type, f))
            c -= len(elements)
            yield from elements

    def read_string(
        self, ctx: DeserializationContext, type_info: TypeInfo, n: int, f: typing.BinaryIO
    ) -> typing.Iterator[typing.Any]:
        b = read(f, 1)
        handler = self.member_record_handlers.get(b[0])
        if handler is None:
            raise UnknownRecord(b[0])
        i, continue_ = handler.deserialize(ctx, f)
        assert continue_
        assert i is not None
        return i

    def read_object(
        self, ctx: DeserializationContext, type_info: TypeInfo, n: int, f: typing.BinaryIO
    ) -> typing.Iterator[typing.Any]:
        b = read(f, 1)
        handler = self.member_record_handlers.get(b[0])
        if handler is None:
            raise UnknownRecord(b[0])
        i, continue_ = handler.deserialize(ctx, f)
        assert continue_
        assert i is not None
        return i

    def read_system_class(
        self, ctx: DeserializationContext, type_info: TypeInfo, n: int, f: typing.BinaryIO
    ) -> typing.Iterator[typing.Any]:
        c = n
        while c > 0:
            elements = list(self.read_member_reference(ctx, f))
            c -= len(elements)
            yield from elements

    def read_class(
        self, ctx: DeserializationContext, type_info: TypeInfo, n: int, f: typing.BinaryIO
    ) -> typing.Iterator[typing.Any]:
        c = n
        while c > 0:
            elements = list(self.read_member_reference(ctx, f))
            c -= len(elements)
            yield from elements

    def read_object_array(
        self, ctx: DeserializationContext, type_info: TypeInfo, n: int, f: typing.BinaryIO
    ) -> typing.Iterator[typing.Any]:
        raise NotImplementedError()

    def read_string_array(
        self, ctx: DeserializationContext, type_info: TypeInfo, n: int, f: typing.BinaryIO
    ) -> typing.Iterator[typing.Any]:
        raise NotImplementedError()

    def read_primitive_array(
        self, ctx: DeserializationContext, type_info: TypeInfo, n: int, f: typing.BinaryIO
    ) -> typing.Iterator[typing.Any]:
        raise NotImplementedError()

    readers: typing.Mapping[
        BinaryType,
        typing.Callable[
            ["_ElementValueReader", DeserializationContext, TypeInfo, int, typing.BinaryIO],
            typing.Iterator[typing.Any],
        ],
    ] = {
        BinaryType.PRIMITIVE: read_primitive,
        BinaryType.STRING: read_string,
        BinaryType.OBJECT: read_object,
        BinaryType.SYSTEM_CLASS: read_system_class,
        BinaryType.CLASS: read_class,
        BinaryType.OBJECT_ARRAY: read_object_array,
        BinaryType.STRING_ARRAY: read_string_array,
        BinaryType.PRIMITIVE_ARRAY: read_primitive_array,
    }

    def __call__(
        self,
        ctx: DeserializationContext,
        elements: typing.Iterable[TypeInfoAndCardinality],
        f: typing.BinaryIO,
    ) -> typing.Iterable[typing.Any]:
        for type_info, n in elements:
            yield from self.readers[type_info.binary_type](self, ctx, type_info, n, f)

    def __init__(
        self,
        length_prefixed_string_reader: LengthPrefixedStringReader,
        untyped_primitive_type_reader: UntypedPrimitiveValueReader,
        member_record_handlers: typing.Mapping[int, RecordHandler],
    ) -> None:
        self.length_prefixed_string_reader = length_prefixed_string_reader
        self.untyped_primitive_type_reader = untyped_primitive_type_reader
        self.member_record_handlers = member_record_handlers


TOPLEVEL_HANDLERS: typing.Iterable[RecordHandlerFactory] = [
    SerializedStreamHandler,
    ClassWithIdHandler,
    SystemClassWithMembersHandler,
    ClassWithMembersHandler,
    SystemClassWithMembersAndTypesHandler,
    ClassWithMembersAndTypesHandler,
    BinaryObjectStringHandler,
    BinaryArrayHandler,
    MessageEndHandler,
    BinaryLibraryHandler,
    ArraySinglePrimitiveHandler,
    ArraySingleObjectHandler,
    ArraySingleStringHandler,
    MethodCallHandler,
    MethodReturnHandler,
]

MEMBER_RECORD_HANDLERS: typing.Iterable[RecordHandlerFactory] = [
    MemberPrimitiveTypedHandler,
    ClassWithIdHandler,
    SystemClassWithMembersHandler,
    ClassWithMembersHandler,
    SystemClassWithMembersAndTypesHandler,
    ClassWithMembersAndTypesHandler,
    BinaryObjectStringHandler,
    MemberReferenceHandler,
    ObjectNullHandler,
    ObjectNullMultiple256Handler,
    ObjectNullMultipleHandler,
]
