import dataclasses
import typing

from ..cli.models import CLITypeInstance


@dataclasses.dataclass
class TypeDescriptorBase:
    cli_type: typing.Optional[CLITypeInstance] = None


@dataclasses.dataclass
class MemberDescriptor:
    name: str
    namespace: typing.Optional[str]
    type_descriptor: TypeDescriptorBase
    member_name: typing.Optional[str] = None


@dataclasses.dataclass
class BasicTypeDescriptor(TypeDescriptorBase):
    pass


@dataclasses.dataclass
class CompositeTypeDescriptor(TypeDescriptorBase):
    members: typing.Sequence[MemberDescriptor] = dataclasses.field(default_factory=list)
    name_to_member_map: typing.Mapping[str, MemberDescriptor] = dataclasses.field(
        init=False, default_factory=dict
    )

    def __post_init__(self) -> None:
        self.name_to_member_map = {member.name: member for member in self.members}


@dataclasses.dataclass
class ArrayTypeDescriptor(TypeDescriptorBase):
    item_cli_type: typing.Optional[CLITypeInstance] = None
    item_descriptor: typing.Optional[TypeDescriptorBase] = None


@dataclasses.dataclass
class DictionaryTypeDescriptor(TypeDescriptorBase):
    key_cli_type: typing.Optional[CLITypeInstance] = None
    value_cli_type: typing.Optional[CLITypeInstance] = None


@dataclasses.dataclass
class SingletonTypeDescriptor(TypeDescriptorBase):
    pass
