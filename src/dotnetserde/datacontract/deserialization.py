import io
import typing
from xml.sax.xmlreader import InputSource, XMLReader

from ..cli.builtins import Builtins
from ..cli.models import CLIBasicValue, CLITypeInstance
from .handlers import MemberHandler, SentinelHandler
from .models import (
    ArrayTypeDescriptor,
    BasicTypeDescriptor,
    CompositeTypeDescriptor,
    MemberDescriptor,
    SingletonTypeDescriptor,
    TypeDescriptorBase,
)
from .sax import make_parser
from .xsdatatypes import XSDataSerializer, build_default_serializer


class _DeserializationContext:
    parser: XMLReader
    builtins: Builtins
    xs_deserializer: XSDataSerializer

    def type_descriptor_from_cli_type(self, cli_type: CLITypeInstance) -> TypeDescriptorBase:
        namespace = str(cli_type.derived_from.namespace)
        name = cli_type.derived_from.name
        if namespace == "System.Collections" and name == "ArrayList":
            return ArrayTypeDescriptor(
                cli_type=cli_type,
                item_cli_type=self.builtins.SYSTEM_OBJECT,
            )
        elif namespace == "System.Collections.Generic" and name == "List":
            first_ref = cli_type.derived_from.parameters[0]
            return ArrayTypeDescriptor(
                cli_type=cli_type,
                item_cli_type=cli_type.ctx.refs[first_ref.derived_from],
            )
        elif namespace == "System":
            descriptor = self.BUILTIN_TYPE_TO_TYPE_DESCRIPTOR_MAP.get(name)
            if descriptor is not None:
                return descriptor

        return CompositeTypeDescriptor(cli_type=cli_type)

    def xs_type_from_cli_type(self, cli_type: CLITypeInstance) -> str:
        namespace = str(cli_type.derived_from.namespace)
        name = cli_type.derived_from.name

        if namespace == "System":
            if name in ("SByte", "Int16", "Int32", "Int64", "Byte", "Uint16", "Uint32", "Uint64"):
                return "long"
            elif name == "String":
                return "string"
            elif name == "DateTime":
                return "dateTime"
            elif name == "Boolean":
                return "bool"
            elif name in ("Double", "Single"):
                return "double"

        raise NotImplementedError()

    def xs_deserialize(self, type_: str, value: str) -> CLIBasicValue:
        return self.xs_deserializer.deserialize(type_, value)

    def __init__(self, builtins: Builtins, parser: XMLReader) -> None:
        self.builtins = builtins
        self.parser = parser
        self.xs_deserializer = build_default_serializer(builtins)
        self.BUILTIN_TYPE_TO_TYPE_DESCRIPTOR_MAP = {
            "IntPtr": SingletonTypeDescriptor(cli_type=builtins.SYSTEM_INT64),
            "UIntPtr": SingletonTypeDescriptor(cli_type=builtins.SYSTEM_UINT64),
            "SByte": BasicTypeDescriptor(cli_type=builtins.SYSTEM_SBYTE),
            "Int16": BasicTypeDescriptor(cli_type=builtins.SYSTEM_INT16),
            "Int32": BasicTypeDescriptor(cli_type=builtins.SYSTEM_INT32),
            "Int64": BasicTypeDescriptor(cli_type=builtins.SYSTEM_INT64),
            "Byte": BasicTypeDescriptor(cli_type=builtins.SYSTEM_BYTE),
            "Uint16": BasicTypeDescriptor(cli_type=builtins.SYSTEM_UINT16),
            "Uint32": BasicTypeDescriptor(cli_type=builtins.SYSTEM_UINT32),
            "Uint64": BasicTypeDescriptor(cli_type=builtins.SYSTEM_UINT64),
            "Single": BasicTypeDescriptor(cli_type=builtins.SYSTEM_SINGLE),
            "Double": BasicTypeDescriptor(cli_type=builtins.SYSTEM_DOUBLE),
            "String": BasicTypeDescriptor(cli_type=builtins.SYSTEM_STRING),
            "DateTime": BasicTypeDescriptor(cli_type=builtins.SYSTEM_DATETIME),
            "TimeSpan": BasicTypeDescriptor(cli_type=builtins.SYSTEM_TIMESPAN),
        }


class Deserializer:
    builtins: Builtins

    def __call__(
        self, f: typing.Union[typing.BinaryIO, typing.TextIO, bytes, str], descriptor: MemberDescriptor
    ):
        parser = make_parser()
        ctx = _DeserializationContext(self.builtins, parser)
        sentinel = SentinelHandler(ctx)
        parser.setContentHandler(MemberHandler(sentinel, ctx, descriptor))
        is_ = InputSource()
        if isinstance(f, bytes):
            f = io.BytesIO(f)
        elif isinstance(f, str):
            f = io.StringIO(f)
        if hasattr(f, "encoding"):
            is_.setCharacterStream(f)
        else:
            is_.setByteStream(f)
        parser.parse(is_)
        return sentinel.result

    def __init__(self, builtins: Builtins) -> None:
        self.builtins = builtins
