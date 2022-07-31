import io

from ..models import Instance


def test_deserialize(fixture):
    from ..instances import deserializer

    ctx = deserializer(io.BytesIO(fixture))
    assert ctx.root_id == 1
    assert ctx.major_version == 1
    assert ctx.minor_version == 0
    assert ctx.header_id == -1
    assert 1 in ctx.objects
    assert isinstance(ctx.objects[1], Instance)
