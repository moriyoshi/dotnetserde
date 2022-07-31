import dataclasses
import enum
import re
import typing

from ..cli import (
    ARRAY_TYPE,
    ROOT_NAMESPACE,
    SYSTEM_COLLECTIONS_GENERIC_DICTIONARY,
    SYSTEM_COLLECTIONS_GENERIC_KEYVALUEPAIR,
    SYSTEM_COLLECTIONS_GENERIC_LIST,
    SYSTEM_COLLECTIONS_GENERIC_NAMESPACE,
    SYSTEM_COLLECTIONS_NAMESPACE,
    SYSTEM_NAMESPACE,
    Builtins,
    CLIBasicValue,
    CLINamespace,
    CLIType,
    CLITypeInstance,
    CLITypeMember,
    CLITypeParam,
    CLITypeResolutionContext,
    CLIValue,
)
from .exceptions import BridgeError
from .models import (
    Array,
    ArrayInfo,
    BinaryArrayType,
    BinaryType,
    ClassInfo,
    ClassTypeInfo,
    Instance,
    LibraryInfo,
    MemberInfo,
    ObjectReference,
    PrimitiveType,
    TypeInfo,
)
from .types import DeserializationResult


class PropertiesRepr(typing.NamedTuple):
    items: typing.Sequence[str]
    mappings: typing.Mapping[str, str]


def parse_properties(csv: typing.Iterable[typing.Union[typing.List, str]]) -> PropertiesRepr:
    items: typing.List[str] = []
    mappings: typing.Dict[str, str] = {}

    items_part = True
    for c in csv:
        if not isinstance(c, str):
            raise BridgeError(f"invalid property representation: {csv}")
        k, s, v = c.strip().partition("=")
        if items_part:
            if s:
                items_part = False
            else:
                items.append(c)

        if not items_part:
            if not s:
                raise BridgeError(f"invalid property representation: {csv}")
            mappings[k] = v

    return PropertiesRepr(items, mappings)


def build_library_info_from_property_dict(repr_: PropertiesRepr) -> LibraryInfo:
    return LibraryInfo(
        name=repr_.items[-1],
        version=repr_.mappings["Version"],
        culture=repr_.mappings["Culture"],
        public_key_token=repr_.mappings.get("PublicKeyToken"),
    )


def build_concrete_class_info_from_property_dict(
    repr_: PropertiesRepr,
) -> typing.Tuple[str, typing.Optional[LibraryInfo]]:
    if len(repr_.items) == 1:
        if repr_.mappings:
            raise BridgeError(f"invalid property representation: {repr_}")
        return (repr_.items[0], None)
    else:
        if len(repr_.items) != 2:
            raise BridgeError(f"invalid property representation: {repr_}")
        return (
            repr_.items[0],
            build_library_info_from_property_dict(repr_._replace(items=repr_.items[1:])),
        )


class ClassNameToken(enum.IntEnum):
    TERMINAL = 0
    LITERAL = 1
    WHITESPACE = 2
    COMMA = 3
    LBRACKET = 4
    RBRACKET = 5


def tokenize_class_name(value: str) -> typing.Iterator[typing.Tuple[ClassNameToken, int, str]]:
    col = 0
    for m in re.finditer(r"[ \t]+|[\[\],]|[^\[\], \t]+", value):
        c = m.group(0)
        if c == " " or c == "\t":
            yield (ClassNameToken.WHITESPACE, col, c)
        elif c == ",":
            yield (ClassNameToken.COMMA, col, c)
        elif c == "[":
            yield (ClassNameToken.LBRACKET, col, c)
        elif c == "]":
            yield (ClassNameToken.RBRACKET, col, c)
        else:
            yield (ClassNameToken.LITERAL, col, c)
        col += len(c)
    yield (ClassNameToken.TERMINAL, col, "")


@dataclasses.dataclass(frozen=True, eq=True)
class ParametrizedClassInfo:
    name: str
    parameters: typing.Sequence["ParametrizedClassInfo"]
    library: typing.Optional[LibraryInfo] = None


class _ClassNameParserDispatch(typing.Protocol):
    def __call__(
        self, t: typing.Tuple[ClassNameToken, int, str]
    ) -> typing.Optional["_ClassNameParserDispatch"]:
        ...  # pragma: nocover


def _parse_class_name_into_intermediate_form(value: str) -> typing.List[typing.Union[typing.List, str]]:
    tokens: typing.List[typing.Union[typing.List, str]] = []
    stack: typing.List[typing.List[typing.Union[typing.List, str]]] = []

    def state_0(t: typing.Tuple[ClassNameToken, int, str]) -> typing.Optional[_ClassNameParserDispatch]:
        nonlocal tokens, stack
        if t[0] == ClassNameToken.WHITESPACE:
            return state_0
        elif t[0] == ClassNameToken.COMMA:
            raise BridgeError(f"unexpected token {t[0].name} at column {t[1] + 1}: {value}")
        elif t[0] == ClassNameToken.LBRACKET:
            stack.append(tokens)
            tokens = []
            return state_0
        elif t[0] == ClassNameToken.RBRACKET:
            if not stack:
                raise BridgeError(f"unexpected token {t[0].name} at column {t[1] + 1}: {value}")
            _tokens = tokens
            tokens = stack.pop()
            tokens.append(_tokens)
            return state_1
        elif t[0] == ClassNameToken.LITERAL:
            tokens.append(t[2])
            return state_1
        elif t[0] == ClassNameToken.TERMINAL:
            if stack:
                raise BridgeError(f"unclosed bracket: {value}")
            return None
        raise AssertionError()

    def state_1(t: typing.Tuple[ClassNameToken, int, str]) -> typing.Optional[_ClassNameParserDispatch]:
        if t[0] == ClassNameToken.WHITESPACE:
            return state_1
        elif t[0] == ClassNameToken.COMMA:
            return state_0
        elif t[0] == ClassNameToken.LBRACKET or t[0] == ClassNameToken.RBRACKET:
            buf.append(t)
            return state_0
        elif t[0] == ClassNameToken.TERMINAL:
            return None
        else:
            raise BridgeError(f"unexpected token {t[0].name} at column {t[1] + 1}: {value}")

    dispatch: _ClassNameParserDispatch = state_0
    buf: typing.List[typing.Tuple[ClassNameToken, int, str]] = []
    i = tokenize_class_name(value)

    while dispatch is not None:
        t: typing.Optional[typing.Tuple[ClassNameToken, int, str]]
        if buf:
            t = buf.pop()
        else:
            t = next(i, None)
            if t is None:
                break

        dispatch = typing.cast(_ClassNameParserDispatch, dispatch(t))

    return tokens


@dataclasses.dataclass
class _ParametrizedClassInfo:
    name: str
    library: typing.Optional[LibraryInfo] = None
    parameters: typing.List["_ParametrizedClassInfo"] = dataclasses.field(default_factory=list)


def _parse_class_name_with_arity(token: str) -> typing.Tuple[str, int]:
    arity = 0
    name, sep, _arity = token.partition("`")
    if sep:
        try:
            arity = int(_arity)
        except ValueError:
            raise BridgeError(f"invalid arity: {_arity}")
    return name, arity


def _parse_class_name_inner(
    tokens: typing.Sequence[typing.Union[typing.List, str]], i: int = 0
) -> typing.Tuple[int, _ParametrizedClassInfo]:
    if i >= len(tokens):
        raise BridgeError("unexpected end of tokens")

    token = tokens[i]
    internal_class_info: _ParametrizedClassInfo
    if isinstance(token, str):
        name, arity = _parse_class_name_with_arity(token)
        internal_class_info = _ParametrizedClassInfo(name)
    else:
        name_and_arity, library = build_concrete_class_info_from_property_dict(parse_properties(token))
        name, arity = _parse_class_name_with_arity(name_and_arity)
        internal_class_info = _ParametrizedClassInfo(name, library)

    i += 1

    if arity > 0:
        if i >= len(tokens):
            raise BridgeError("unexpected end of tokens")

        inner_tokens = tokens[i]
        i += 1
        j = 0

        while len(internal_class_info.parameters) < arity:
            if j >= len(inner_tokens):
                raise BridgeError("unexpected end of tokens")
            j, param_type = _parse_class_name_inner(inner_tokens, j)
            internal_class_info.parameters.append(param_type)

        if j < len(inner_tokens):
            raise BridgeError(f"redundant token {inner_tokens[j:]}")

    return i, internal_class_info


def _convert_into_parametrized_class_info(internal_class_info: _ParametrizedClassInfo) -> ParametrizedClassInfo:
    return ParametrizedClassInfo(
        name=internal_class_info.name,
        parameters=tuple(
            _convert_into_parametrized_class_info(param_type) for param_type in internal_class_info.parameters
        ),
        library=internal_class_info.library,
    )


def parse_class_name(value: str) -> ParametrizedClassInfo:
    _, internal_class_info = _parse_class_name_inner(_parse_class_name_into_intermediate_form(value))
    return _convert_into_parametrized_class_info(internal_class_info)


def split_into_namespace_and_name(qualified_name: str) -> typing.Tuple[str, str]:
    namespace_or_name, sep, name = qualified_name.rpartition(".")
    if not sep:
        if namespace_or_name == "":
            raise BridgeError("invalid qualified type name: {qualified_name}")
        return "", namespace_or_name
    else:
        if name == "":
            raise BridgeError("invalid qualified type name: {qualified_name}")
        return namespace_or_name, name


class Bridge:
    result: DeserializationResult
    _builtins: Builtins
    _p_class_to_cli_type_mappings: typing.Dict[
        typing.Tuple[
            str,
            typing.Optional[LibraryInfo],
            int,
        ],
        CLIType,
    ]
    _p_class_to_cli_type_instance_mappings: typing.Dict[ParametrizedClassInfo, CLITypeInstance]
    _array_types: typing.Dict[typing.Tuple[int, int], CLITypeInstance]
    _namespaces: typing.Dict[str, CLINamespace]
    _objects: typing.Dict[int, CLIValue]
    _primitive_type_to_cli_type_instance_builtin_mappings: typing.Dict[PrimitiveType, CLITypeInstance]

    def _lookup_namespace(self, namespace: str) -> CLINamespace:
        retval = self._namespaces.get(namespace)
        if retval is None:
            parent, sep, name = namespace.rpartition(".")
            if sep is None:
                retval = CLINamespace(name, ROOT_NAMESPACE)
            else:
                retval = CLINamespace(name, self._lookup_namespace(parent))
            self._namespaces[namespace] = retval
        return retval

    def _build_cli_type_members(
        self,
        members: typing.Collection[MemberInfo],
    ) -> typing.Sequence[CLITypeMember]:
        return tuple(
            CLITypeMember(
                name=mi.name,
                type=self._get_cli_type_instance_for_type_info(mi.type_info),
            )
            for mi in members
        )

    def _get_cli_type_instance_for_parametrized_class_info(
        self,
        p_class_info: ParametrizedClassInfo,
        members: typing.Collection[MemberInfo] = (),
    ) -> CLITypeInstance:
        ti = self._p_class_to_cli_type_instance_mappings.get(p_class_info)
        if ti is not None:
            return ti

        t_key = (p_class_info.name, p_class_info.library, len(p_class_info.parameters))
        t = self._p_class_to_cli_type_mappings.get(t_key)
        if t is None:
            namespace, name = split_into_namespace_and_name(p_class_info.name)
            t = CLIType(
                name=name,
                namespace=self._lookup_namespace(namespace),
                members=self._build_cli_type_members(members),
                parameters={CLITypeParam(f"T{n + 1}"): None for n in range(len(p_class_info.parameters))},
            )
            self._p_class_to_cli_type_mappings[t_key] = t
        else:
            if not t.intrinsic and not t.members and members:
                t = t.replace(members=self._build_cli_type_members(members))
                self._p_class_to_cli_type_mappings[t_key] = t
        unknown_parameters = [
            param.derived_from
            for param, resolvable in zip(t.parameters, t.resolved_parameters)
            if resolvable is None
        ]
        if len(unknown_parameters) != len(p_class_info.parameters):
            raise BridgeError(
                f"invalid number of type parameters for {p_class_info.name}:"
                f" {len(unknown_parameters)} expected, got {len(p_class_info.parameters)}"
            )
        ti = t.instantiate(
            dict(
                zip(
                    unknown_parameters,
                    (
                        self._get_cli_type_instance_for_parametrized_class_info(param_type)
                        for param_type in p_class_info.parameters
                    ),
                )
            ),
        )
        self._p_class_to_cli_type_instance_mappings[p_class_info] = ti
        return ti

    def _get_cli_type_instance_for_class_info(self, info: ClassInfo) -> CLITypeInstance:
        library_info: typing.Optional[LibraryInfo] = None
        if info.library_id is not None:
            library_name = self.result.library_id_name_mappings[info.library_id]
            library_info = build_library_info_from_property_dict(parse_properties(library_name.split(",")))
        p_class_info = parse_class_name(info.name)
        if library_info is not None:
            if p_class_info.library is not None:
                raise BridgeError("invalid class info")
            p_class_info = dataclasses.replace(p_class_info, library=library_info)
        return self._get_cli_type_instance_for_parametrized_class_info(p_class_info, info.members)

    def _get_cli_type_instance_for_type_info(self, info: TypeInfo) -> CLITypeInstance:
        if info.binary_type == BinaryType.PRIMITIVE:
            prim_type = typing.cast(PrimitiveType, info.additional_info)
            return self._primitive_type_to_cli_type_instance_builtin_mappings[prim_type]
        elif info.binary_type == BinaryType.STRING:
            return self._builtins.SYSTEM_STRING
        elif info.binary_type == BinaryType.CLASS:
            class_type_info = typing.cast(ClassTypeInfo, info.additional_info)
            return self._get_cli_type_instance_for_class_type_info(class_type_info)
        elif info.binary_type == BinaryType.SYSTEM_CLASS:
            p_class_info = parse_class_name(typing.cast(str, info.additional_info))
            return self._get_cli_type_instance_for_parametrized_class_info(p_class_info)
        elif info.binary_type == BinaryType.OBJECT:
            return self._builtins.SYSTEM_OBJECT
        else:
            raise NotImplementedError(info)

    def _get_array_type(self, elem_type: CLITypeInstance, depth: int) -> CLITypeInstance:
        at_key = (id(elem_type), 0)
        ti = self._array_types.get(at_key)
        if ti is not None:
            return ti
        ti = ARRAY_TYPE.instantiate([elem_type])
        self._array_types[at_key] = ti
        return ti

    def _get_cli_type_instance_for_array_info(self, info: ArrayInfo) -> CLITypeInstance:
        if info.type != BinaryArrayType.SINGLE:
            raise NotImplementedError()
        if len(info.shape) != 1:
            raise NotImplementedError()
        assert info.type_info is not None
        elem_type = self._get_cli_type_instance_for_type_info(info.type_info)
        return self._get_array_type(elem_type, 0)

    def _get_cli_type_instance_for_class_type_info(self, info: ClassTypeInfo) -> CLITypeInstance:
        library_info: typing.Optional[LibraryInfo] = None
        if info.library_id is not None:
            library_name = self.result.library_id_name_mappings[info.library_id]
            library_info = build_library_info_from_property_dict(parse_properties(library_name.split(",")))
        p_class_info = parse_class_name(info.name)
        if library_info is not None:
            if p_class_info.library is not None:
                raise BridgeError("invalid class info")
            p_class_info = dataclasses.replace(p_class_info, library=library_info)
        return self._get_cli_type_instance_for_parametrized_class_info(p_class_info)

    def _convert_array_list_value(self, ti: CLITypeInstance, v: typing.Any) -> CLIValue:
        value = self._convert_value(v.values[0])
        len_ = v.values[1]
        if not isinstance(value, CLIBasicValue) or value.type_instance.derived_from.origin != ARRAY_TYPE:
            raise BridgeError(
                f"the value of the first member of {ti} must be an array," f" got {type(value.type_instance)}"
            )
        return ti.instantiate(value.value[:len_])

    def _convert_dictionary_value(self, ti: CLITypeInstance, v: typing.Any) -> CLIValue:
        value = self._convert_value(v.values[3])
        if not isinstance(value, CLIBasicValue) or value.type_instance.derived_from.origin != ARRAY_TYPE:
            raise BridgeError(
                f"the value of the first member of {ti} must be an array," f" got {type(value.type_instance)}"
            )
        _value: typing.List[typing.Tuple[CLIValue, CLIValue]] = []
        for pair in value.value:
            if pair is None:
                continue
            assert len(pair.value) == 2
            _value.append(pair.value)
        return ti.instantiate(_value)

    def _convert_key_value_pair_value(self, ti: CLITypeInstance, v: typing.Any) -> CLIValue:
        _values = tuple(self._convert_value(value) for value in v.values)
        if len(_values) != 2:
            raise BridgeError(f"value for {ti} must have a two element sequence")
        return ti.instantiate(_values)

    def _convert_value(self, v: typing.Any) -> CLIValue:
        value: CLIValue
        object_id: int
        if isinstance(v, Instance):
            ti = self._get_cli_type_instance_for_class_info(v.class_info)
            if ti.derived_from.intrinsic:
                if v.values is None:
                    raise BridgeError("{ti} must have a value")
                if ti == self._builtins.SYSTEM_COLLECTIONS_ARRAYLIST:
                    value = self._convert_array_list_value(ti, v)
                elif ti.derived_from.origin == SYSTEM_COLLECTIONS_GENERIC_LIST:
                    value = self._convert_array_list_value(ti, v)
                elif ti.derived_from.origin == SYSTEM_COLLECTIONS_GENERIC_DICTIONARY:
                    value = self._convert_dictionary_value(ti, v)
                elif ti.derived_from.origin == SYSTEM_COLLECTIONS_GENERIC_KEYVALUEPAIR:
                    value = self._convert_key_value_pair_value(ti, v)
                else:
                    raise NotImplementedError()
            else:
                value = ti.instantiate(
                    member_dict=(
                        {mi.name: self._convert_value(_v) for mi, _v in zip(v.class_info.members, v.values)}
                        if v.values is not None
                        else None
                    ),
                )
            object_id = v.class_info.object_id
        elif isinstance(v, Array):
            ti = self._get_cli_type_instance_for_array_info(v.array_info)
            _values: typing.List[CLIValue]
            if v.values is not None:
                if len(v.values) != v.array_info.shape[0]:
                    raise BridgeError(
                        f"array element count does not match with the shape:"
                        f"{len(v.values)} vs {v.array_info.shape[0]}"
                    )
                _values = [self._convert_value(e) for e in v.values]
            else:
                _values = [self._convert_value(None)] * v.array_info.shape[0]

            value = ti.instantiate(_values)
            object_id = v.array_info.object_id
        elif isinstance(v, ObjectReference):
            return self._get_value_for_object_id(v.object_id)
        else:
            return self._builtins.from_python_value(v)
        self._objects[object_id] = value
        return value

    def _get_value_for_object_id(self, object_id: int) -> CLIValue:
        v = self._objects.get(object_id)
        if v is not None:
            return v
        return self._convert_value(self.result.objects[object_id])

    def get(self, id_: int) -> CLIValue:
        return self._convert_value(self.result.objects[id_])

    def __call__(self) -> CLIValue:
        if self.result.root_id is None:
            raise BridgeError("root_id is not specified by DeserializationContext")
        return self._convert_value(self.result.objects[self.result.root_id])

    def __init__(self, result: DeserializationResult) -> None:
        self.result = result
        self._builtins = Builtins(CLITypeResolutionContext())
        self._p_class_to_cli_type_mappings = {
            ("System.Collections.Generic.List", None, 1): SYSTEM_COLLECTIONS_GENERIC_LIST,
            ("System.Collections.Generic.Dictionary", None, 2): SYSTEM_COLLECTIONS_GENERIC_DICTIONARY,
            ("System.Collections.Generic.KeyValuePair", None, 2): SYSTEM_COLLECTIONS_GENERIC_KEYVALUEPAIR,
        }
        self._p_class_to_cli_type_instance_mappings = {
            ParametrizedClassInfo(
                "System.Collections.ArrayList", (), None
            ): self._builtins.SYSTEM_COLLECTIONS_ARRAYLIST,
            ParametrizedClassInfo(
                "System.Collections.Dictionary", (), None
            ): self._builtins.SYSTEM_COLLECTIONS_DICTIONARY,
            ParametrizedClassInfo("System.Object", (), None): self._builtins.SYSTEM_OBJECT,
            ParametrizedClassInfo("System.String", (), None): self._builtins.SYSTEM_STRING,
        }
        self._primitive_type_to_cli_type_instance_builtin_mappings = {
            PrimitiveType.BOOLEAN: self._builtins.SYSTEM_BOOLEAN,
            PrimitiveType.BYTE: self._builtins.SYSTEM_BYTE,
            PrimitiveType.CHAR: self._builtins.SYSTEM_CHAR,
            PrimitiveType.DATETIME: self._builtins.SYSTEM_DATETIME,
            PrimitiveType.DECIMAL: self._builtins.SYSTEM_DECIMAL,
            PrimitiveType.DOUBLE: self._builtins.SYSTEM_DOUBLE,
            PrimitiveType.INT16: self._builtins.SYSTEM_INT16,
            PrimitiveType.INT32: self._builtins.SYSTEM_INT32,
            PrimitiveType.INT64: self._builtins.SYSTEM_INT64,
            PrimitiveType.NULL: self._builtins.SYSTEM_OBJECT,
            PrimitiveType.SBYTE: self._builtins.SYSTEM_SBYTE,
            PrimitiveType.SINGLE: self._builtins.SYSTEM_SINGLE,
            PrimitiveType.STRING: self._builtins.SYSTEM_STRING,
            PrimitiveType.TIMESPAN: self._builtins.SYSTEM_TIMESPAN,
            PrimitiveType.UINT16: self._builtins.SYSTEM_UINT16,
            PrimitiveType.UINT32: self._builtins.SYSTEM_UINT32,
            PrimitiveType.UINT64: self._builtins.SYSTEM_UINT64,
        }
        self._array_types = {}
        self._namespaces = {
            "": ROOT_NAMESPACE,
            "System": SYSTEM_NAMESPACE,
            "System.Collections": SYSTEM_COLLECTIONS_NAMESPACE,
            "System.Collections.Generic": SYSTEM_COLLECTIONS_GENERIC_NAMESPACE,
        }
        self._objects = {}
