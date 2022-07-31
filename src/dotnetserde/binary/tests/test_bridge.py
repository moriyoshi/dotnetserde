import datetime
import io

from ...cli.models import CLIBasicValue, CLICompositeObject


def test_bridge_1(fixture):
    from ..bridge import Bridge
    from ..instances import deserializer

    result = Bridge(deserializer(io.BytesIO(fixture)))()
    assert isinstance(result, CLICompositeObject)
    assert str(result.type_instance) == "Some.Name.Space.Bar"
    assert len(result.members) == 2
    assert (
        str(result.members[0].type_instance.derived_from)
        == "System.Collections.Generic.List<Some.Name.Space.Foo>"
    )
    assert isinstance(result.members[0], CLIBasicValue)
    assert len(result.members[0].value) == 1
    assert isinstance(result.members[0].value[0], CLICompositeObject)
    assert str(result.members[0].value[0].type_instance) == "Some.Name.Space.Foo"
    assert (
        str(result.members[1].type_instance.derived_from)
        == "System.Collections.Generic.List<System.DateTime>"
    )
    assert len(result.members[1].value) == 1
    assert isinstance(result.members[1].value[0], CLIBasicValue)
    assert result.members[1].value[0].value.astimezone(datetime.timezone.utc) == datetime.datetime(
        2022, 8, 15, 23, 23, 26, 372019, tzinfo=datetime.timezone.utc
    )


def test_bridge_2(fixture2):
    from ..bridge import Bridge
    from ..instances import deserializer

    result = Bridge(deserializer(io.BytesIO(fixture2)))()
    assert isinstance(result, CLICompositeObject)
    assert str(result.type_instance) == "Some.Name.Space.Noo"
    assert len(result.members) == 1
    assert len(result.members[0].value) == 1
    assert result.members[0].value[0][0].value == "test"
    assert str(result.members[0].value[0][1].type_instance) == "Some.Name.Space.Foo"
