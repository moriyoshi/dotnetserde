import pytest

from ...cli.builtins import (
    ROOT_NAMESPACE,
    SYSTEM_COLLECTIONS_GENERIC_DICTIONARY,
    SYSTEM_COLLECTIONS_GENERIC_LIST,
    Builtins,
)
from ...cli.models import (
    CLIBasicValue,
    CLICompositeObject,
    CLINamespace,
    CLIType,
    CLITypeMember,
    CLITypeResolutionContext,
)
from ..models import (
    ArrayTypeDescriptor,
    BasicTypeDescriptor,
    CompositeTypeDescriptor,
    DictionaryTypeDescriptor,
    MemberDescriptor,
)


@pytest.fixture
def resolution_context():
    return CLITypeResolutionContext()


@pytest.fixture
def builtins(resolution_context):
    return Builtins(resolution_context)


@pytest.fixture
def cli_ns_foo_bar():
    return CLINamespace(
        name="Bar",
        namespace=CLINamespace(
            name="Foo",
            namespace=ROOT_NAMESPACE,
        ),
    )


@pytest.fixture
def cli_ns_some_name_space():
    return CLINamespace(
        name="Space",
        namespace=CLINamespace(
            name="Name",
            namespace=CLINamespace(
                name="Some",
                namespace=ROOT_NAMESPACE,
            ),
        ),
    )


@pytest.fixture
def cli_type_foo(cli_ns_foo_bar):
    return CLIType(
        name="Foo",
        namespace=cli_ns_foo_bar,
    )


@pytest.fixture
def composite_root_object():
    return """<?xml version="1.0"?>
<X xmlns="http://schemas.datacontract.org/2004/07/Foo.Bar" xmlns:i="http://www.w3.org/2001/XMLSchema-instance">
  <hey xmlns:a="http://schemas.microsoft.com/2003/10/Serialization/Arrays">
    <a:anyType xmlns:b="http://www.w3.org/2001/XMLSchema" i:type="b:dateTime">2022-08-08T22:57:56.192121+09:00</a:anyType>
    <a:anyType xmlns:b="http://www.w3.org/2001/XMLSchema" i:type="b:base64Binary">AQID</a:anyType>
    <a:anyType i:nil="true"/>
    <a:anyType/>
  </hey>
  <x xmlns:a="http://schemas.datacontract.org/2004/07/System">
    <a:IntPtr>
      <value xmlns="" xmlns:b="http://www.w3.org/2001/XMLSchema" i:type="b:long">1</value>
    </a:IntPtr>
  </x>
  <y>1</y>
  <z xmlns:a="http://schemas.datacontract.org/2004/07/Foo">
    <a:Foo/>
  </z>
</X>"""  # noqa: E501


@pytest.fixture
def descriptor_for_composite_root_object(cli_ns_foo_bar, cli_type_foo, builtins):
    T = SYSTEM_COLLECTIONS_GENERIC_LIST.get_parameter_by_name("T")

    return MemberDescriptor(
        name="X",
        namespace="http://schemas.datacontract.org/2004/07/Foo.Bar",
        type_descriptor=CompositeTypeDescriptor(
            cli_type=CLIType(
                name="X",
                namespace=cli_ns_foo_bar,
                members=[
                    CLITypeMember(
                        name="a",
                        type=SYSTEM_COLLECTIONS_GENERIC_LIST.partial({T: builtins.SYSTEM_OBJECT}),
                    ),
                    CLITypeMember(
                        name="x",
                        type=SYSTEM_COLLECTIONS_GENERIC_LIST.partial({T: builtins.SYSTEM_INTPTR}),
                    ),
                    CLITypeMember(
                        name="y",
                        type=builtins.SYSTEM_INT32,
                    ),
                    CLITypeMember(
                        name="z",
                        type=SYSTEM_COLLECTIONS_GENERIC_LIST.partial(
                            {
                                T: cli_type_foo,
                            }
                        ).instantiate(),
                    ),
                ],
            ).instantiate(),
            members=[
                MemberDescriptor(
                    name="hey",
                    namespace="http://schemas.datacontract.org/2004/07/Foo.Bar",
                    member_name="a",
                    type_descriptor=ArrayTypeDescriptor(),
                ),
                MemberDescriptor(
                    name="x",
                    namespace="http://schemas.datacontract.org/2004/07/Foo.Bar",
                    member_name="x",
                    type_descriptor=ArrayTypeDescriptor(),
                ),
                MemberDescriptor(
                    name="y",
                    namespace="http://schemas.datacontract.org/2004/07/Foo.Bar",
                    member_name="y",
                    type_descriptor=BasicTypeDescriptor(),
                ),
                MemberDescriptor(
                    name="z",
                    namespace="http://schemas.datacontract.org/2004/07/Foo.Bar",
                    member_name="z",
                    type_descriptor=ArrayTypeDescriptor(),
                ),
            ],
        ),
    )


@pytest.fixture
def plain_root_object():
    return """<?xml version="1.0"?>
<X
  xmlns="http://schemas.datacontract.org/2004/07/Foo.Bar"
  xmlns:a="http://www.w3.org/2001/XMLSchema"
  xmlns:i="http://www.w3.org/2001/XMLSchema-instance"
  i:type="a:base64Binary">
    AQIDBA==
</X>
"""


@pytest.fixture
def descriptor_for_plain_root_object(cli_ns_foo_bar, builtins):
    return MemberDescriptor(
        name="X",
        namespace="http://schemas.datacontract.org/2004/07/Foo.Bar",
        type_descriptor=BasicTypeDescriptor(
            cli_type=builtins.SYSTEM_BYTE_ARRAY.instantiate(),
        ),
    )


@pytest.fixture
def composite_root_with_dictionary_member():
    return """<?xml version="1.0"?>
<Noo xmlns="http://schemas.datacontract.org/2004/07/Some.Name.Space"
     xmlns:i="http://www.w3.org/2001/XMLSchema-instance">
  <foos xmlns:a="http://schemas.microsoft.com/2003/10/Serialization/Arrays">
    <a:KeyValueOfstringFoopRLFEb3Q>
      <a:Key>test</a:Key>
      <a:Value/>
    </a:KeyValueOfstringFoopRLFEb3Q>
  </foos>
</Noo>"""


@pytest.fixture
def descriptor_for_composite_root_with_dictionary_member(cli_ns_some_name_space, cli_type_foo, builtins):
    return MemberDescriptor(
        name="Noo",
        namespace="http://schemas.datacontract.org/2004/07/Some.Name.Space",
        type_descriptor=CompositeTypeDescriptor(
            cli_type=CLIType(
                name="Noo",
                namespace=cli_ns_some_name_space,
                members=[
                    CLITypeMember(
                        name="foos",
                        type=SYSTEM_COLLECTIONS_GENERIC_DICTIONARY.instantiate(
                            [builtins.SYSTEM_STRING, cli_type_foo.instantiate()]
                        ),
                    ),
                ],
            ).instantiate(),
            members=[MemberDescriptor("foos", None, DictionaryTypeDescriptor())],
        ),
    )


@pytest.fixture
def target(builtins):
    from ..deserialization import Deserializer

    return Deserializer(builtins)


def test_composite_root(target, descriptor_for_composite_root_object, composite_root_object):
    result = target(composite_root_object, descriptor_for_composite_root_object)
    assert isinstance(result, CLICompositeObject)
    assert isinstance(result["a"], CLIBasicValue)
    assert len(result["a"].value) == 4
    assert all(isinstance(v, CLIBasicValue) for v in result["a"].value)
    assert len(result["x"].value) == 1
    assert result["x"].value[0].value == 1
    assert result["y"].value == 1
    assert isinstance(result["z"].value[0], CLICompositeObject)
    assert (
        result["z"].value[0].type_instance.derived_from
        == descriptor_for_composite_root_object.type_descriptor.cli_type[
            "z"
        ].derived_from.type.derived_from.resolved_parameters[0]
    )


def test_plain_root(target, descriptor_for_plain_root_object, plain_root_object):
    result = target(plain_root_object, descriptor_for_plain_root_object)
    assert isinstance(result, CLIBasicValue)
    assert result.value == b"\x01\x02\x03\x04"


def test_composite_root_with_dictionary_member(
    target, descriptor_for_composite_root_with_dictionary_member, composite_root_with_dictionary_member
):
    result = target(composite_root_with_dictionary_member, descriptor_for_composite_root_with_dictionary_member)
    assert isinstance(result, CLICompositeObject)
    assert isinstance(result["foos"], CLIBasicValue)
    assert (
        str(result["foos"].type_instance) == "System.Collections.Generic.Dictionary<System.String, Foo.Bar.Foo>"
    )
    assert result["foos"].value[0].value[0].value == "test"
    assert str(result["foos"].value[0].value[1].type_instance) == "Foo.Bar.Foo"
