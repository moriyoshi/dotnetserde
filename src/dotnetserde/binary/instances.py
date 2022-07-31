import typing

from ..utils import localize_timezone
from .deserialization import Deserializer
from .handlers import (
    MEMBER_RECORD_HANDLERS,
    TOPLEVEL_HANDLERS,
    _ClassInfoReader,
    _ClassTypeInfoReader,
    _ElementValueReader,
    _LengthPrefixedStringReader,
    _MemberTypeInfoReader,
    _UntypedPrimitiveValueReader,
    read_array_info,
)
from .types import RecordHandler, RecordHandlerFactoryArgs


def build_deserializer() -> Deserializer:
    member_record_handlers: typing.Dict[int, RecordHandler] = {}
    length_prefixed_string_reader = _LengthPrefixedStringReader(encoding="utf-8")
    class_info_reader = _ClassInfoReader(
        length_prefixed_string_reader=length_prefixed_string_reader,
    )
    class_type_info_reader = _ClassTypeInfoReader(
        length_prefixed_string_reader=length_prefixed_string_reader,
    )
    member_type_info_reader = _MemberTypeInfoReader(
        length_prefixed_string_reader=length_prefixed_string_reader,
        class_type_info_reader=class_type_info_reader,
    )
    untyped_primitive_value_reader = _UntypedPrimitiveValueReader(
        length_prefixed_string_reader=length_prefixed_string_reader,
        timezone_localizer=localize_timezone,
    )
    element_value_reader = _ElementValueReader(
        length_prefixed_string_reader=length_prefixed_string_reader,
        untyped_primitive_type_reader=untyped_primitive_value_reader,
        member_record_handlers=member_record_handlers,
    )
    kwargs = RecordHandlerFactoryArgs(
        length_prefixed_string_reader=length_prefixed_string_reader,
        class_info_reader=class_info_reader,
        class_type_info_reader=class_type_info_reader,
        member_type_info_reader=member_type_info_reader,
        untyped_primitive_value_reader=untyped_primitive_value_reader,
        element_value_reader=element_value_reader,
        array_info_reader=read_array_info,
        member_record_handlers=member_record_handlers,
    )

    member_record_handlers.update(
        (handler.CODE, handler)
        for handler in (handler_factory(**kwargs) for handler_factory in MEMBER_RECORD_HANDLERS)
    )

    deserializer = Deserializer(handler_class(**kwargs) for handler_class in TOPLEVEL_HANDLERS)

    return deserializer


deserializer = build_deserializer()
