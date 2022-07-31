from ..exceptions import DotNetSerdeException


class BinaryFormatterError(DotNetSerdeException):
    pass


class UnexpectedEOF(BinaryFormatterError):
    expected_length: int
    actual_length: int

    @property
    def message(self) -> str:
        return (
            f"unexpected end of stream. expected {self.expected_length} bytes,"
            f" but only found {self.actual_length} bytes."
        )

    def __str__(self) -> str:
        return self.message

    def __init__(self, expected_length: int, actual_length: int) -> None:
        super().__init__(expected_length, actual_length)
        self.expected_length = expected_length
        self.actual_length = actual_length


class VersionMismatch(BinaryFormatterError):
    pass


class InvalidStreamError(BinaryFormatterError):
    pass


class UnknownRecord(InvalidStreamError):
    cdoe: int

    @property
    def message(self) -> str:
        return f"unknown record code {self.code}"

    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


class UnresolvableLibraryId(BinaryFormatterError):
    library_id: int

    @property
    def message(self) -> str:
        return f"unresolvable library id {self.library_id}"

    def __init__(self, library_id: int) -> None:
        super().__init__(library_id)
        self.library_id = library_id


class BridgeError(DotNetSerdeException):
    pass
