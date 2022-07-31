import abc
import collections.abc
import dataclasses
import itertools
import typing
from pydoc import resolve

from ..utils import raise_exception


@dataclasses.dataclass(frozen=True)
class CLINamespace:
    name: str
    namespace: typing.Optional["CLINamespace"] = None

    def __str__(self) -> str:
        outer_namespace = str(self.namespace) if self.namespace is not None else ""
        return (outer_namespace + "." if outer_namespace else "") + self.name


@dataclasses.dataclass(frozen=True)
class CLITypeParam:
    name: typing.Optional[str]


@dataclasses.dataclass(frozen=True)
class BoundCLITypeParam:
    derived_from: CLITypeParam
    ordinal: int
    bound_to: "CLIType"

    @property
    def name(self) -> typing.Optional[str]:
        return self.derived_from.name


@dataclasses.dataclass
class CLITypeResolutionContext:
    resolved: typing.Dict[int, "CLITypeInstance"] = dataclasses.field(default_factory=dict)
    refs: typing.Dict[CLITypeParam, "CLITypeInstance"] = dataclasses.field(default_factory=dict)
    reprs: typing.Dict[int, str] = dataclasses.field(default_factory=dict)


class CLITypeResolvable(typing.Protocol):
    def stringify(self, ctx: CLITypeResolutionContext) -> str:
        ...  # pragma: nocover

    def resolve(self, ctx: CLITypeResolutionContext) -> "CLITypeInstance":
        ...  # pragma: nocover


@dataclasses.dataclass(frozen=True)
class CLITypeBinding:
    ref: CLITypeParam

    def stringify(self, ctx: CLITypeResolutionContext) -> str:
        return self.resolve(ctx).stringify(ctx)

    def resolve(self, ctx: CLITypeResolutionContext) -> "CLITypeInstance":
        p = ctx.refs.get(self.ref)
        if p is None:
            raise ValueError(f"type parameter '{self.ref}' is unbound")
        return p.resolve(ctx)


@dataclasses.dataclass(frozen=True)
class CLITypeMember:
    name: str
    type: "CLITypeResolvable"


@dataclasses.dataclass(frozen=True)
class BoundCLITypeMember:
    derived_from: CLITypeMember
    ordinal: int
    bound_to: "CLIType"

    @property
    def name(self) -> str:
        return self.derived_from.name

    @property
    def type(self) -> CLITypeResolvable:
        return self.derived_from.type


class BoundCLITypeParamView:
    _items: typing.Sequence[BoundCLITypeParam]
    _cache: typing.Dict[typing.Union[str, CLITypeParam], BoundCLITypeParam]

    @typing.overload
    def __getitem__(self, index: int) -> BoundCLITypeParam:
        ...  # pragma: nocover

    @typing.overload
    def __getitem__(self, name: str) -> BoundCLITypeParam:
        ...  # pragma: nocover

    @typing.overload
    def __getitem__(self, param: CLITypeParam) -> BoundCLITypeParam:
        ...  # pragma: nocover

    def __getitem__(self, index_or_name_or_param: typing.Union[int, str, CLITypeParam]) -> BoundCLITypeParam:
        if isinstance(index_or_name_or_param, int):
            return self._items[index_or_name_or_param]
        elif isinstance(index_or_name_or_param, str):
            i = self._cache.get(index_or_name_or_param)
            if i is None:
                for item in self._items:
                    if item.name == index_or_name_or_param:
                        return item
                raise KeyError(f"{self} has no member {index_or_name_or_param}")
            return i
        else:
            i = self._cache.get(index_or_name_or_param)
            if i is None:
                for item in self._items:
                    if item.derived_from == index_or_name_or_param:
                        return item
                raise KeyError(f"{self} has no member {index_or_name_or_param}")
            return i

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> typing.Iterator[BoundCLITypeParam]:
        return iter(self._items)

    def __init__(self, items: typing.Sequence[BoundCLITypeParam]) -> None:
        self._items = items
        self._cache = {}


class Nothing:
    pass


NOTHING = Nothing()


class CLIType:
    name: str
    namespace: CLINamespace
    parameters: BoundCLITypeParamView
    resolved_parameters: typing.Sequence[typing.Optional[CLITypeResolvable]]
    default_parameters: typing.Sequence[typing.Optional[CLITypeResolvable]]
    intrinsic: bool
    members: typing.Sequence[BoundCLITypeMember]
    derived_from: typing.Optional["CLIType"]
    member_handler: typing.Optional[
        typing.Callable[["CLITypeInstance", typing.Sequence["CLIValue"]], typing.Any]
    ]
    _name_cache: typing.Dict[str, BoundCLITypeMember]

    @property
    def origin(self) -> "CLIType":
        return self.derived_from if self.derived_from is not None else self

    @typing.overload
    def __getitem__(self, index: int) -> BoundCLITypeMember:
        ...  # pragma: nocover

    @typing.overload
    def __getitem__(self, name: str) -> BoundCLITypeMember:
        ...  # pragma: nocover

    def __getitem__(self, index_or_name: typing.Union[int, str]) -> BoundCLITypeMember:
        if isinstance(index_or_name, int):
            return self.members[index_or_name]
        else:
            i = self._name_cache.get(index_or_name)
            if i is None:
                try:
                    i = next(member for member in self.members if member.name == index_or_name)
                except StopIteration:
                    raise KeyError(f"{self} has no member {index_or_name}")
            return i

    def __str__(self) -> str:
        return self.stringify(CLITypeResolutionContext())

    def stringify(self, ctx: CLITypeResolutionContext) -> str:
        s = ctx.reprs.get(id(self))
        if s is not None:
            return s

        ctx.reprs[id(self)] = "..."  # sentinel
        if self.parameters:
            param_list = (
                "<"
                + ", ".join(p.stringify(ctx) if p is not None else "?" for p in self.resolved_parameters)
                + ">"
            )
        else:
            param_list = ""
        namespace = str(self.namespace)
        if namespace:
            namespace += "."
        s = ctx.reprs[id(self)] = f"{namespace}{self.name}{param_list}"
        return s

    def resolve(self, ctx: CLITypeResolutionContext) -> "CLITypeInstance":
        resolved = ctx.resolved.get(id(self))
        if resolved is not None:
            return resolved

        for param, resolvable in zip(self.parameters, self.resolved_parameters):
            if resolvable is None:
                raise ValueError(f"{self} has unresolved parameters")
            ctx.refs[param.derived_from] = resolvable.resolve(ctx)

        ctx.resolved[id(self)] = resolved = CLITypeInstance(
            ctx=ctx,
            derived_from=self,
        )
        return resolved

    def partial(
        self,
        parameters: typing.Union[
            typing.Collection[CLITypeResolvable], typing.Mapping[CLITypeParam, CLITypeResolvable]
        ],
    ) -> "CLIType":
        new_resolved_parameters: typing.Sequence[typing.Optional[CLITypeResolvable]]

        if isinstance(parameters, collections.abc.Mapping):
            new_resolved_parameters = tuple(
                parameters.get(bound_param.derived_from)
                if resolvable is None
                else (
                    resolvable
                    if parameters.get(bound_param.derived_from) is None
                    else raise_exception(lambda: ValueError(f"{self} already has a value for {bound_param}"))
                )
                for bound_param, resolvable in zip(self.parameters, self.resolved_parameters)
            )
        else:
            if len(parameters) > len(self.parameters):
                raise ValueError(f"expected at most {len(self.parameters)} parameters, got {len(parameters)}")
            new_resolved_parameters = tuple(
                p
                if resolvable is None
                else (
                    resolvable
                    if p is None
                    else raise_exception(lambda: ValueError(f"{self} already has a value for {bound_param}"))
                )
                for bound_param, resolvable, p in itertools.zip_longest(
                    self.parameters, self.resolved_parameters, parameters, fillvalue=None
                )
            )

        return self.replace(
            resolved_parameters=new_resolved_parameters,
            members=[m.derived_from for m in self.members],
            derived_from=self,
        )

    def replace(
        self,
        name: typing.Union[str, Nothing] = NOTHING,
        namespace: typing.Union[CLINamespace, Nothing] = NOTHING,
        parameters: typing.Union[
            typing.Collection[CLITypeParam],
            typing.Mapping[CLITypeParam, CLITypeResolvable],
            Nothing,
        ] = NOTHING,
        default_parameters: typing.Union[
            typing.Collection[typing.Optional[CLITypeResolvable]],
            typing.Mapping[CLITypeParam, CLITypeResolvable],
            Nothing,
        ] = NOTHING,
        resolved_parameters: typing.Union[
            typing.Collection[typing.Optional[CLITypeResolvable]],
            None,
            Nothing,
        ] = NOTHING,
        intrinsic: typing.Union[bool, Nothing] = NOTHING,
        members: typing.Union[typing.Iterable[CLITypeMember], Nothing] = NOTHING,
        derived_from: typing.Union["CLIType", None, Nothing] = NOTHING,
        member_handler: typing.Union[
            typing.Callable[["CLITypeInstance", typing.Sequence["CLIValue"]], typing.Any],
            None,
            Nothing,
        ] = NOTHING,
    ) -> "CLIType":
        return CLIType(
            name=self.name if isinstance(name, Nothing) else name,
            namespace=self.namespace if isinstance(namespace, Nothing) else namespace,
            parameters=(
                [p.derived_from for p in self.parameters] if isinstance(parameters, Nothing) else parameters
            ),
            default_parameters=self.default_parameters,
            resolved_parameters=(
                self.resolved_parameters if isinstance(resolved_parameters, Nothing) else resolved_parameters
            ),
            intrinsic=self.intrinsic if isinstance(intrinsic, Nothing) else intrinsic,
            members=([m.derived_from for m in self.members] if isinstance(members, Nothing) else members),
            derived_from=self.derived_from if isinstance(derived_from, Nothing) else derived_from,
            member_handler=self.member_handler if isinstance(member_handler, Nothing) else member_handler,
        )

    def instantiate(
        self,
        parameters: typing.Union[
            typing.Collection[CLITypeResolvable], typing.Mapping[CLITypeParam, CLITypeResolvable]
        ] = (),
    ) -> "CLITypeInstance":
        return self.partial(parameters).resolve(CLITypeResolutionContext())

    def get_parameter_by_name(self, name: str) -> typing.Optional[CLITypeParam]:
        for k in self.parameters:
            if k.name == name:
                return k.derived_from

        return None

    def __init__(
        self,
        name: str,
        namespace: CLINamespace,
        parameters: typing.Union[
            typing.Collection[CLITypeParam], typing.Mapping[CLITypeParam, CLITypeResolvable]
        ] = (),
        default_parameters: typing.Union[
            typing.Collection[typing.Optional[CLITypeResolvable]],
            typing.Mapping[CLITypeParam, CLITypeResolvable],
        ] = (),
        resolved_parameters: typing.Optional[typing.Collection[typing.Optional[CLITypeResolvable]]] = None,
        intrinsic: bool = False,
        members: typing.Iterable[CLITypeMember] = (),
        derived_from: typing.Optional["CLIType"] = None,
        member_handler: typing.Optional[
            typing.Callable[["CLITypeInstance", typing.Sequence["CLIValue"]], typing.Any]
        ] = None,
    ) -> None:
        self.name = name
        self.namespace = namespace
        self.intrinsic = intrinsic
        self.derived_from = derived_from
        self.member_handler = member_handler

        _parameters: typing.Sequence[BoundCLITypeParam]
        _default_parameters: typing.Sequence[typing.Optional[CLITypeResolvable]]
        _resolved_parameters: typing.Sequence[typing.Optional[CLITypeResolvable]]

        if isinstance(parameters, collections.abc.Mapping):
            if resolved_parameters:
                raise ValueError(
                    "cannot specify both 'parameters' and 'resolved_parameters'" " if 'parameters' is a mapping"
                )
            _parameters = tuple(
                BoundCLITypeParam(
                    derived_from=param,
                    ordinal=i,
                    bound_to=self,
                )
                for i, param in enumerate(parameters.keys())
            )
            _resolved_parameters = tuple(parameters.values())
        else:
            _parameters = tuple(
                BoundCLITypeParam(
                    derived_from=param,
                    ordinal=i,
                    bound_to=self,
                )
                for i, param in enumerate(parameters)
            )
            if resolved_parameters is not None:
                if len(parameters) != len(resolved_parameters):
                    raise ValueError(
                        "element counts for 'parameters' and 'resolved_parameters'"
                        " must be the same if they are both sequences"
                    )
                _resolved_parameters = tuple(resolved_parameters)
            else:
                _resolved_parameters = (None,) * len(parameters)

        if isinstance(default_parameters, collections.abc.Mapping):
            _default_parameters = tuple(
                default_parameters.get(bound_param.derived_from, None) for bound_param in _parameters
            )
        else:
            if len(default_parameters) > len(_parameters):
                raise ValueError(
                    "element counts for 'default_parameters'" " is greater than that of 'parameters'"
                )
            _default_parameters = tuple(
                resolvable
                for _, resolvable in itertools.zip_longest(
                    _parameters,
                    default_parameters,
                    fillvalue=None,
                )
            )

        for a, b, bound_param in zip(_resolved_parameters, _default_parameters, _parameters):
            if a is not None and b is not None:
                raise ValueError(
                    f"default parameter '{bound_param.name}' shall shadow the corresponding bound parameter,"
                    f" which is not permitted"
                )

        _members = tuple(
            BoundCLITypeMember(
                derived_from=member,
                ordinal=i,
                bound_to=self,
            )
            for i, member in enumerate(members)
        )

        self.parameters = BoundCLITypeParamView(_parameters)
        self.resolved_parameters = _resolved_parameters
        self.default_parameters = _default_parameters
        self.members = _members

        self._name_cache = {}


@dataclasses.dataclass(frozen=True)
class CLITypeInstanceMember:
    derived_from: BoundCLITypeMember
    type: "CLITypeInstance"

    @property
    def ordinal(self) -> int:
        return self.derived_from.ordinal

    @property
    def name(self) -> str:
        return self.derived_from.name


class CLITypeInstanceMemberCollectionView(collections.abc.Sequence, typing.Sequence[CLITypeInstanceMember]):
    type_instance: "CLITypeInstance"
    _cache: typing.List[typing.Optional[CLITypeInstanceMember]]

    @typing.overload
    def __getitem__(self, index: int) -> CLITypeInstanceMember:
        ...  # pragma: nocover

    @typing.overload
    def __getitem__(self, index: str) -> CLITypeInstanceMember:
        ...  # pragma: nocover

    @typing.overload
    def __getitem__(self, slice: slice) -> typing.Sequence[CLITypeInstanceMember]:
        ...  # pragma: nocover

    def __getitem__(
        self, index_or_slice: typing.Union[int, str, slice]
    ) -> typing.Union[CLITypeInstanceMember, typing.Sequence[CLITypeInstanceMember]]:
        if isinstance(index_or_slice, int):
            i = self._cache[index_or_slice]
            if i is None:
                derived_from = self.type_instance.derived_from[index_or_slice]
                i = CLITypeInstanceMember(
                    derived_from=derived_from,
                    type=derived_from.type.resolve(self.type_instance.ctx),
                )
                self._cache[index_or_slice] = i
            return i
        elif isinstance(index_or_slice, str):
            return self[self.type_instance.derived_from[index_or_slice].ordinal]
        else:
            return [self[i] for i in range(*index_or_slice.indices(len(self)))]

    def __len__(self) -> int:
        return len(self.type_instance.derived_from.members)

    def __init__(self, type_instance: "CLITypeInstance") -> None:
        self.type_instance = type_instance
        self._cache = [None] * len(self.type_instance.derived_from.members)


class CLITypeInstance:
    ctx: CLITypeResolutionContext
    derived_from: CLIType
    builtin_name: typing.Optional[str] = None
    member_handler: typing.Optional[
        typing.Callable[["CLITypeInstance", typing.Sequence["CLIValue"]], typing.Any]
    ]

    @property
    def members(self) -> CLITypeInstanceMemberCollectionView:
        return CLITypeInstanceMemberCollectionView(self)

    @typing.overload
    def __getitem__(self, index: int) -> CLITypeInstanceMember:
        ...  # pragma: nocover

    @typing.overload
    def __getitem__(self, name: str) -> CLITypeInstanceMember:
        ...  # pragma: nocover

    def __getitem__(self, index_or_name: typing.Union[int, str]) -> CLITypeInstanceMember:
        return self.members[index_or_name]

    def __str__(self) -> str:
        return self.derived_from.stringify(self.ctx)

    def stringify(self, ctx: CLITypeResolutionContext) -> str:
        return self.derived_from.stringify(self.ctx)

    def resolve(self, ctx: CLITypeResolutionContext) -> "CLITypeInstance":
        return self

    def instantiate(
        self,
        value: typing.Optional[typing.Any] = None,
        member_values: typing.Optional[typing.Iterable["CLIValue"]] = None,
        member_dict: typing.Optional[typing.Mapping[str, "CLIValue"]] = None,
    ) -> "CLIValue":
        if member_values is None:
            if self.derived_from.members:
                if member_dict is not None:
                    member_values = tuple(
                        v for _, v in sorted(member_dict.items(), key=lambda pair: self[pair[0]].ordinal)
                    )
        else:
            if member_dict is not None:
                raise ValueError("cannot specify member_values and member_dict at the same time")
            member_values = tuple(member_values)

        if self.derived_from.intrinsic:
            if member_values:
                if self.member_handler is None:
                    raise ValueError(f"{self} is an intrinsic type and no member_handler is provided")
                value = self.member_handler(self, member_values)
            return CLIBasicValue(self, value)
        else:
            if member_values is None and self.members:
                raise ValueError(f"either member_values or member_dict must be specified for {self}")
            return CLICompositeObject(type_instance=self, members=member_values or ())

    def __init__(
        self,
        ctx: CLITypeResolutionContext,
        derived_from: CLIType,
        builtin_name: typing.Optional[str] = None,
        member_handler: typing.Optional[
            typing.Callable[["CLITypeInstance", typing.Sequence["CLIValue"]], typing.Any]
        ] = None,
    ) -> None:
        self.ctx = ctx
        self.derived_from = derived_from
        self.builtin_name = builtin_name
        self.member_handler = member_handler or derived_from.member_handler


@dataclasses.dataclass
class CLIValue(abc.ABC):
    type_instance: CLITypeInstance


@dataclasses.dataclass
class CLIBasicValue(CLIValue):
    value: typing.Any


@dataclasses.dataclass
class CLINullValue(CLIValue):
    pass


@dataclasses.dataclass
class CLICompositeObject(CLIValue):
    members: typing.Sequence[CLIValue] = dataclasses.field(default=())

    @typing.overload
    def __getitem__(self, index: int) -> CLIValue:
        ...  # pragma: nocover

    @typing.overload
    def __getitem__(self, name: str) -> CLIValue:
        ...  # pragma: nocover

    def __getitem__(self, index_or_name: typing.Union[int, str]) -> CLIValue:
        if isinstance(index_or_name, int):
            return self.members[index_or_name]
        else:
            return self.members[self.type_instance[index_or_name].ordinal]

    def __post_init__(self):
        if len(self.members) != len(self.type_instance.derived_from.members):
            raise ValueError(
                f"given values does not match to the member count"
                f" (got {len(self.members)},"
                f" {len(self.type_instance.derived_from.members)} expected)"
            )


ROOT_NAMESPACE = CLINamespace("")

INTERNAL_NAMESPACE = CLINamespace("__internal__")

ARRAY_TYPE = CLIType(
    name="Array",
    namespace=INTERNAL_NAMESPACE,
    intrinsic=True,
    parameters={CLITypeParam("T"): None},
)


def array_of(type_instance: CLITypeInstance) -> CLITypeInstance:
    return ARRAY_TYPE.instantiate([type_instance])
