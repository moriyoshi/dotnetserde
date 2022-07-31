import pytest


@pytest.fixture
def resolution_context():
    from ..models import CLITypeResolutionContext

    return CLITypeResolutionContext()


@pytest.fixture
def builtins(resolution_context):
    from ..builtins import Builtins

    return Builtins(resolution_context)


@pytest.fixture
def T():
    from ..models import CLITypeParam

    return CLITypeParam("T")


@pytest.fixture
def t1(T):
    from ..models import ROOT_NAMESPACE, CLIType, CLITypeBinding, CLITypeMember

    return CLIType(
        name="GenericType",
        namespace=ROOT_NAMESPACE,
        parameters={T: None},
        members=(CLITypeMember("mem0", CLITypeBinding(T)),),
    )


@pytest.fixture
def t2():
    from ..models import ROOT_NAMESPACE, CLIType

    return CLIType(
        name="Intrinsic1",
        namespace=ROOT_NAMESPACE,
    )


@pytest.fixture
def t3():
    from ..models import ROOT_NAMESPACE, CLIType

    return CLIType(
        name="Intrinsic2",
        namespace=ROOT_NAMESPACE,
    )


@pytest.fixture
def t4(T, t1, t2, t3):
    from ..models import ROOT_NAMESPACE, CLIType, CLITypeMember

    return CLIType(
        name="CompositeType",
        namespace=ROOT_NAMESPACE,
        members=(
            CLITypeMember("mem0", t1.partial({T: t2})),
            CLITypeMember("mem1", t1.partial({T: t3})),
        ),
    )


def test_generic_type(T, t1, t2, resolution_context):
    from ..models import ROOT_NAMESPACE

    with pytest.raises(ValueError):
        t1.resolve(resolution_context)

    pt = t1.partial({T: t2})

    assert pt.name == "GenericType"
    assert pt.namespace == ROOT_NAMESPACE
    assert pt.resolved_parameters[pt.parameters[T].ordinal] is t2

    ti = pt.instantiate()

    assert str(ti) == "GenericType<Intrinsic1>"


@pytest.fixture
def t(T, t1, t2):
    return t1.instantiate({T: t2})


def test_generic_type_instantiate(t, builtins):
    from ..models import CLIBasicValue

    i = t.instantiate(
        member_dict={
            "mem0": CLIBasicValue(builtins.SYSTEM_INT32, 123),
        }
    )
    assert i.members[0].value == 123


def test_composite_type_containing_generic_type_members_instantiate(T, t4):
    i = t4.instantiate()

    assert i.members[0].type.derived_from.resolved_parameters[0].name == "Intrinsic1"
    assert i.members[1].type.derived_from.resolved_parameters[0].name == "Intrinsic2"
