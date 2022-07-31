import typing

from .exceptions import UnexpectedEOF, UnknownRecord
from .types import DeserializationResult, RecordHandler


class _DeserializationContext:
    root_id: typing.Optional[int] = None
    header_id: typing.Optional[int] = None
    major_version: typing.Optional[int] = None
    minor_version: typing.Optional[int] = None
    library_id_name_mappings: typing.Dict[int, str]
    objects: typing.Dict[int, typing.Any]

    def set_header(self, root_id: int, header_id: int, major_version: int, minor_version: int) -> None:
        self.root_id = root_id
        self.header_id = header_id
        self.major_version = major_version
        self.minor_version = minor_version

    def add_library_id_name_mapping(self, id_: int, name: str) -> None:
        self.library_id_name_mappings[id_] = name

    def library_id_resolvable(self, id_: int) -> bool:
        return id_ in self.library_id_name_mappings

    def add_object(self, id_: int, instance: typing.Any) -> None:
        self.objects[id_] = instance

    def fetch_object(self, id_: int) -> typing.Any:
        return self.objects[id_]

    def __init__(self) -> None:
        self.library_id_name_mappings = {}
        self.objects = {}


class Deserializer:
    def __call__(self, f: typing.BinaryIO) -> DeserializationResult:
        ctx = _DeserializationContext()
        continue_ = True
        while continue_:
            code_bin = f.read(1)
            if len(code_bin) < 1:
                raise UnexpectedEOF(1, len(code_bin))
            code = int(code_bin[0])
            handler = self.code_to_handler_map.get(code)
            if handler is None:
                raise UnknownRecord(code)
            i, continue_ = handler.deserialize(ctx, f)
            if i is not None:
                for _ in i:
                    pass
        return ctx

    def __init__(self, handlers: typing.Iterable[RecordHandler]) -> None:
        self.code_to_handler_map = {handler.CODE: handler for handler in handlers}
