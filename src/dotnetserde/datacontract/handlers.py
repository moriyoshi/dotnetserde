import dataclasses
import typing
import xml.sax.handler as sax_handler
from xml.sax.xmlreader import XMLReader

from ..cli.builtins import SYSTEM_COLLECTIONS_GENERIC_KEYVALUEPAIR
from ..cli.models import CLIBasicValue, CLITypeInstance
from .exceptions import InvalidDataContractPayload
from .models import (
    ArrayTypeDescriptor,
    BasicTypeDescriptor,
    CompositeTypeDescriptor,
    DictionaryTypeDescriptor,
    MemberDescriptor,
    SingletonTypeDescriptor,
    TypeDescriptorBase,
)

# https://docs.microsoft.com/en-us/dotnet/framework/wcf/feature-details/using-data-contracts

DC_NAMESPACE_PREFIX = "http://schemas.datacontract.org/2004/07/"
DC_NAMESPACE_ARRAY = "http://schemas.microsoft.com/2003/10/Serialization/Arrays"
XMLSCHEMA_NAMESPACE = "http://www.w3.org/2001/XMLSchema"
XMLSCHEMA_INSTANCE_NAMESPACE = "http://www.w3.org/2001/XMLSchema-instance"


class DeserializationContext(typing.Protocol):
    parser: XMLReader

    def type_descriptor_from_cli_type(self, cli_type: CLITypeInstance) -> TypeDescriptorBase:
        ...  # pragma: nocover

    def xs_type_from_cli_type(self, cli_type: CLITypeInstance) -> str:
        ...  # pragma: nocover

    def xs_deserialize(self, type_: str, value: str) -> CLIBasicValue:
        ...  # pragma: nocover


class BaseHandler(sax_handler.ContentHandler):
    outer: typing.Optional["BaseHandler"]
    ctx: DeserializationContext
    _xmlns: typing.Dict[str, str]

    @property
    def _namespace(self) -> typing.Optional[str]:
        if self.outer is None:
            return None
        else:
            return self.outer._namespace

    def startPrefixMapping(self, prefix: str, uri: str) -> None:
        self._xmlns[prefix] = uri

    def endElementNS(self, name: str, qname: typing.Optional[str]) -> None:
        self.ctx.parser.setContentHandler(self.outer)

    def push_value(self, value: typing.Any) -> None:
        if self.outer is not None:
            self.outer.push_value(value)

    def __init__(self, outer: typing.Optional["BaseHandler"], ctx: DeserializationContext) -> None:
        self.outer = outer
        self.ctx = ctx
        self._xmlns = dict(outer._xmlns) if outer is not None else {}


class SentinelHandler(BaseHandler):
    result: typing.Any = None

    def endElementNS(self, name: str, qname: typing.Optional[str]) -> None:
        pass

    def push_value(self, value: typing.Any) -> None:
        self.result = value

    def __init__(self, ctx: DeserializationContext) -> None:
        super().__init__(None, ctx)


# https://docs.microsoft.com/en-us/dotnet/framework/wcf/feature-details/collection-types-in-data-contracts
class CollectionItemHandler(BaseHandler):
    def startElementNS(
        self,
        name: typing.Tuple[str, str],
        qname: typing.Optional[str],
        attrs: typing.Mapping[typing.Tuple[str, str], str],
    ) -> None:
        pass


class CompositeObjectHandler(BaseHandler):
    descriptor: CompositeTypeDescriptor
    _member: typing.Optional[MemberDescriptor] = None
    _member_value_dict: typing.Dict[int, typing.Any] = {}

    def startElementNS(
        self,
        name: typing.Tuple[str, str],
        qname: typing.Optional[str],
        attrs: typing.Mapping[typing.Tuple[str, str], str],
    ) -> None:
        assert self.descriptor.cli_type is not None
        member = self.descriptor.name_to_member_map[name[1]]
        member_name = member.member_name or member.name
        if member.type_descriptor.cli_type is None:
            member = dataclasses.replace(
                member,
                type_descriptor=dataclasses.replace(
                    member.type_descriptor,
                    cli_type=self.descriptor.cli_type.members[member_name].type,
                ),
            )
        handler = MemberHandler(
            self,
            self.ctx,
            member,
        )
        self._member = member
        self.ctx.parser.setContentHandler(handler)
        handler.startElementNS(name, qname, attrs)

    def endElementNS(self, name: str, qname: typing.Optional[str]) -> None:
        cli_type = self.descriptor.cli_type
        assert cli_type is not None
        _cli_type = cli_type  # to handle mypy bug

        super().push_value(
            _cli_type.instantiate(
                member_values=[
                    v
                    for k, v in sorted(
                        self._member_value_dict.items(),
                        key=lambda pair: _cli_type[pair[0]].ordinal,
                    )
                ],
            )
        )
        super().endElementNS(name, qname)

    def push_value(self, value: typing.Any) -> None:
        if self._member is not None:
            assert self.descriptor.cli_type is not None
            member_name = self._member.member_name or self._member.name
            cli_type = self.descriptor.cli_type[member_name]
            self._member_value_dict[cli_type.ordinal] = value

    def __init__(
        self,
        outer: typing.Optional["BaseHandler"],
        ctx: DeserializationContext,
        descriptor: CompositeTypeDescriptor,
    ) -> None:
        super().__init__(outer, ctx)
        self.descriptor = descriptor
        self._member_value_dict = {}


class ArrayObjectHandler(BaseHandler):
    descriptor: ArrayTypeDescriptor
    _anonymous_member: MemberDescriptor
    _items: typing.List[typing.Any]

    def startElementNS(
        self,
        name: typing.Tuple[str, str],
        qname: typing.Optional[str],
        attrs: typing.Mapping[typing.Tuple[str, str], str],
    ) -> None:
        handler = MemberHandler(
            self,
            self.ctx,
            self._anonymous_member,
        )
        self.ctx.parser.setContentHandler(handler)
        handler.startElementNS(name, qname, attrs)

    def endElementNS(self, name: str, qname: typing.Optional[str]) -> None:
        assert self.descriptor.cli_type is not None
        super().push_value(self.descriptor.cli_type.instantiate(self._items))
        super().endElementNS(name, qname)

    def push_value(self, value: typing.Any) -> None:
        self._items.append(value)

    def __init__(
        self,
        outer: typing.Optional["BaseHandler"],
        ctx: DeserializationContext,
        descriptor: TypeDescriptorBase,
    ) -> None:
        super().__init__(outer, ctx)
        assert isinstance(descriptor, ArrayTypeDescriptor)
        self.descriptor = descriptor
        item_cli_type = self.descriptor.item_cli_type
        if item_cli_type is None:
            container_cli_type = self.descriptor.cli_type
            assert container_cli_type is not None
            assert len(container_cli_type.derived_from.parameters) == 1
            _item_cli_type = container_cli_type.derived_from.resolved_parameters[0]
            assert _item_cli_type is not None
            item_cli_type = _item_cli_type.resolve(container_cli_type.ctx)

        if descriptor.item_descriptor is not None:
            item_descriptor = descriptor.item_descriptor
            if item_descriptor.cli_type is None:
                if item_cli_type is None:
                    raise ValueError("cannot infer item type for {descriptor}")
                item_descriptor = dataclasses.replace(item_descriptor, cli_type=item_cli_type)
        else:
            item_descriptor = ctx.type_descriptor_from_cli_type(item_cli_type)

        self._anonymous_member = MemberDescriptor(
            name="*",
            namespace=None,
            type_descriptor=item_descriptor,
        )
        self._items = []


class DictionaryObjectHandler(BaseHandler):
    descriptor: DictionaryTypeDescriptor
    _anonymous_member: MemberDescriptor
    _items: typing.List[typing.Tuple[typing.Any, typing.Any]]

    def startElementNS(
        self,
        name: typing.Tuple[str, str],
        qname: typing.Optional[str],
        attrs: typing.Mapping[typing.Tuple[str, str], str],
    ) -> None:
        handler = MemberHandler(
            self,
            self.ctx,
            self._anonymous_member,
        )
        self.ctx.parser.setContentHandler(handler)
        handler.startElementNS(name, qname, attrs)

    def endElementNS(self, name: str, qname: typing.Optional[str]) -> None:
        assert self.descriptor.cli_type is not None
        super().push_value(self.descriptor.cli_type.instantiate(self._items))
        super().endElementNS(name, qname)

    def push_value(self, value: typing.Any) -> None:
        self._items.append(value)

    def __init__(
        self,
        outer: typing.Optional["BaseHandler"],
        ctx: DeserializationContext,
        descriptor: TypeDescriptorBase,
    ) -> None:
        super().__init__(outer, ctx)
        assert isinstance(descriptor, DictionaryTypeDescriptor)
        self.descriptor = descriptor
        key_cli_type = self.descriptor.key_cli_type
        value_cli_type = self.descriptor.value_cli_type
        if key_cli_type is None:
            assert value_cli_type is None
            container_cli_type = self.descriptor.cli_type
            assert container_cli_type is not None
            assert len(container_cli_type.derived_from.parameters) == 2
            _key_cli_type, _value_cli_type = container_cli_type.derived_from.resolved_parameters
            assert _key_cli_type is not None and _value_cli_type is not None
            key_cli_type = _key_cli_type.resolve(container_cli_type.ctx)
            value_cli_type = _value_cli_type.resolve(container_cli_type.ctx)

        assert value_cli_type is not None
        self._anonymous_member = MemberDescriptor(
            name="*",
            namespace=None,
            type_descriptor=CompositeTypeDescriptor(
                cli_type=SYSTEM_COLLECTIONS_GENERIC_KEYVALUEPAIR.instantiate([key_cli_type, value_cli_type]),
                members=[
                    MemberDescriptor(
                        name="Key",
                        namespace=None,
                        type_descriptor=ctx.type_descriptor_from_cli_type(key_cli_type),
                    ),
                    MemberDescriptor(
                        name="Value",
                        namespace=None,
                        type_descriptor=ctx.type_descriptor_from_cli_type(value_cli_type),
                    ),
                ],
            ),
        )
        self._items = []


class SingletonObjectHandler(BaseHandler):
    descriptor: TypeDescriptorBase
    _anonymous_member: MemberDescriptor

    def startElementNS(
        self,
        name: typing.Tuple[str, str],
        qname: typing.Optional[str],
        attrs: typing.Mapping[typing.Tuple[str, str], str],
    ) -> None:
        handler = MemberHandler(
            self,
            self.ctx,
            self._anonymous_member,
        )
        self.ctx.parser.setContentHandler(handler)
        handler.startElementNS(name, qname, attrs)

    def endElementNS(self, name: str, qname: typing.Optional[str]) -> None:
        super().endElementNS(name, qname)

    def __init__(
        self,
        outer: typing.Optional["BaseHandler"],
        ctx: DeserializationContext,
        descriptor: TypeDescriptorBase,
    ) -> None:
        super().__init__(outer, ctx)
        self.descriptor = descriptor
        cli_type = self.descriptor.cli_type
        assert cli_type is not None
        self._anonymous_member = MemberDescriptor(
            name="*",
            namespace=None,
            type_descriptor=ctx.type_descriptor_from_cli_type(cli_type),
        )


class BasicObjectHandler(BaseHandler):
    type: str
    _chunks: typing.List[str]

    def characters(self, content: str) -> None:
        self._chunks.append(content)

    def startElemenNS(
        self,
        name: typing.Tuple[str, str],
        qname: typing.Optional[str],
        attrs: typing.Mapping[typing.Tuple[str, str], str],
    ) -> None:
        raise InvalidDataContractPayload("basic object may not contain nested elements, got {name}")
        return super().startElement(name, attrs)

    def endElementNS(self, name: str, qname: typing.Optional[str]) -> None:
        assert self.outer is not None
        assert (
            not isinstance(
                self.outer,
                (CompositeObjectHandler, ArrayObjectHandler, SingletonObjectHandler),
            )
            or self.outer.descriptor.cli_type is not None
        )
        value = self.ctx.xs_deserialize(self.type, "".join(self._chunks)) if self._chunks else None
        self.outer.push_value(value)
        super().endElementNS(name, qname)

    def __init__(self, outer: typing.Optional["BaseHandler"], ctx: DeserializationContext, type_: str) -> None:
        super().__init__(outer, ctx)
        self.type = type_
        self._chunks = []


class NilObjectHandler(BaseHandler):
    def characters(self, content: str) -> None:
        raise InvalidDataContractPayload("a nil object cannot have a content")

    def endElementNS(self, name: str, qname: typing.Optional[str]) -> None:
        assert self.outer is not None and isinstance(
            self.outer,
            (CompositeObjectHandler, ArrayObjectHandler, SingletonObjectHandler),
        ), self.outer
        cli_type = self.outer.descriptor.cli_type
        assert cli_type is not None
        self.outer.push_value(CLIBasicValue(cli_type, None))
        super().endElementNS(name, qname)


class MemberHandler(BaseHandler):
    descriptor: MemberDescriptor

    @property
    def _namespace(self) -> typing.Optional[str]:
        if self.descriptor.namespace is not None:
            return self.descriptor.namespace
        else:
            return super()._namespace

    def startElementNS(
        self,
        name: typing.Tuple[str, str],
        qname: typing.Optional[str],
        attrs: typing.Mapping[typing.Tuple[str, str], str],
    ) -> None:
        xsin = attrs.get((XMLSCHEMA_INSTANCE_NAMESPACE, "nil"))
        if xsin is not None and self.ctx.xs_deserialize("bool", xsin):
            self.ctx.parser.setContentHandler(NilObjectHandler(self.outer, self.ctx))
            return

        xsit = attrs.get((XMLSCHEMA_INSTANCE_NAMESPACE, "type"))
        if xsit is not None:
            namespace_prefix, _, type_ = xsit.partition(":")
            ns = self._xmlns[namespace_prefix]
            if ns != XMLSCHEMA_NAMESPACE:
                raise InvalidDataContractPayload(
                    f"XMLSchema instance attribute occurred, "
                    f"but its content refers to unexpected namespace {ns}"
                )
            self.ctx.parser.setContentHandler(BasicObjectHandler(self.outer, self.ctx, type_))
            return

        if isinstance(self.descriptor.type_descriptor, CompositeTypeDescriptor):
            if self._namespace is not None and name[0] != self._namespace:
                raise InvalidDataContractPayload(
                    f"the object's namespace must be under {self.descriptor.namespace}, got {name[0]}"
                )

            if self.descriptor.name != "*" and name[1] != self.descriptor.name:
                raise InvalidDataContractPayload(
                    f"the object's tag name must be {self.descriptor.name}, got {name[1]}"
                )

            self.ctx.parser.setContentHandler(
                CompositeObjectHandler(
                    self.outer,
                    self.ctx,
                    self.descriptor.type_descriptor,
                )
            )
            return

        if isinstance(self.descriptor.type_descriptor, ArrayTypeDescriptor):
            self.ctx.parser.setContentHandler(
                ArrayObjectHandler(
                    self.outer,
                    self.ctx,
                    self.descriptor.type_descriptor,
                )
            )
            return

        if isinstance(self.descriptor.type_descriptor, DictionaryTypeDescriptor):
            self.ctx.parser.setContentHandler(
                DictionaryObjectHandler(
                    self.outer,
                    self.ctx,
                    self.descriptor.type_descriptor,
                )
            )
            return

        if isinstance(self.descriptor.type_descriptor, SingletonTypeDescriptor):
            self.ctx.parser.setContentHandler(
                SingletonObjectHandler(
                    self.outer,
                    self.ctx,
                    self.descriptor.type_descriptor,
                )
            )
            return

        if isinstance(self.descriptor.type_descriptor, BasicTypeDescriptor):
            cli_type = self.descriptor.type_descriptor.cli_type
            assert cli_type is not None
            self.ctx.parser.setContentHandler(
                BasicObjectHandler(
                    self.outer,
                    self.ctx,
                    self.ctx.xs_type_from_cli_type(cli_type),
                )
            )
            return

        raise NotImplementedError()

    def __init__(
        self,
        outer: typing.Optional["BaseHandler"],
        ctx: DeserializationContext,
        descriptor: MemberDescriptor,
    ) -> None:
        super().__init__(outer, ctx)
        self.descriptor = descriptor
