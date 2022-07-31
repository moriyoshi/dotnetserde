import datetime
import decimal
import typing

from .models import (
    ROOT_NAMESPACE,
    CLINamespace,
    CLIType,
    CLITypeBinding,
    CLITypeInstance,
    CLITypeMember,
    CLITypeParam,
    CLITypeResolutionContext,
    CLIValue,
    array_of,
)

SYSTEM_NAMESPACE = CLINamespace(name="System", namespace=ROOT_NAMESPACE)

SYSTEM_COLLECTIONS_NAMESPACE = CLINamespace(name="Collections", namespace=SYSTEM_NAMESPACE)

SYSTEM_COLLECTIONS_GENERIC_NAMESPACE = CLINamespace(name="Generic", namespace=SYSTEM_COLLECTIONS_NAMESPACE)

SYSTEM_BOOLEAN = CLIType("Boolean", SYSTEM_NAMESPACE, intrinsic=True)
SYSTEM_CHAR = CLIType("Char", SYSTEM_NAMESPACE, intrinsic=True)
SYSTEM_STRING = CLIType("String", SYSTEM_NAMESPACE, intrinsic=True)
SYSTEM_SINGLE = CLIType("Single", SYSTEM_NAMESPACE, intrinsic=True)
SYSTEM_DOUBLE = CLIType("Double", SYSTEM_NAMESPACE, intrinsic=True)
SYSTEM_SBYTE = CLIType("SByte", SYSTEM_NAMESPACE, intrinsic=True)
SYSTEM_INT16 = CLIType("Int16", SYSTEM_NAMESPACE, intrinsic=True)
SYSTEM_INT32 = CLIType("Int32", SYSTEM_NAMESPACE, intrinsic=True)
SYSTEM_INT64 = CLIType("Int64", SYSTEM_NAMESPACE, intrinsic=True)
SYSTEM_UINT64 = CLIType("UInt64", SYSTEM_NAMESPACE, intrinsic=True)
SYSTEM_INTPTR = CLIType("IntPtr", SYSTEM_NAMESPACE, intrinsic=True)
SYSTEM_UINTPTR = CLIType("UIntPtr", SYSTEM_NAMESPACE, intrinsic=True)
SYSTEM_BYTE = CLIType("Byte", SYSTEM_NAMESPACE, intrinsic=True)
SYSTEM_UINT16 = CLIType("UInt16", SYSTEM_NAMESPACE, intrinsic=True)
SYSTEM_UINT32 = CLIType("UInt32", SYSTEM_NAMESPACE, intrinsic=True)
SYSTEM_OBJECT = CLIType("Object", SYSTEM_NAMESPACE, intrinsic=True)
SYSTEM_COLLECTIONS_ARRAYLIST = CLIType("ArrayList", SYSTEM_COLLECTIONS_NAMESPACE, intrinsic=True)
SYSTEM_COLLECTIONS_DICTIONARY = CLIType("Dictionary", SYSTEM_COLLECTIONS_NAMESPACE, intrinsic=True)
SYSTEM_COLLECTIONS_GENERIC_LIST = CLIType(
    "List",
    SYSTEM_COLLECTIONS_GENERIC_NAMESPACE,
    parameters=[CLITypeParam("T")],
    intrinsic=True,
)
SYSTEM_COLLECTIONS_GENERIC_DICTIONARY = CLIType(
    "Dictionary",
    SYSTEM_COLLECTIONS_GENERIC_NAMESPACE,
    parameters=[CLITypeParam("TKey"), CLITypeParam("TValue")],
    intrinsic=True,
)

TKey = CLITypeParam("TKey")
TValue = CLITypeParam("TValue")

SYSTEM_COLLECTIONS_GENERIC_KEYVALUEPAIR = CLIType(
    "KeyValuePair",
    SYSTEM_COLLECTIONS_GENERIC_NAMESPACE,
    parameters=[TKey, TValue],
    intrinsic=True,
    members=[
        CLITypeMember("Key", CLITypeBinding(TKey)),
        CLITypeMember("Value", CLITypeBinding(TValue)),
    ],
    member_handler=lambda type_instance, member_values: tuple(member_values),
)
SYSTEM_DATETIME = CLIType(
    "DateTime",
    SYSTEM_NAMESPACE,
    intrinsic=True,
)
SYSTEM_TIMESPAN = CLIType(
    "TimeSpan",
    SYSTEM_NAMESPACE,
    intrinsic=True,
)
SYSTEM_DECIMAL = CLIType(
    "Decimal",
    SYSTEM_NAMESPACE,
    intrinsic=True,
)


class Builtins:
    ctx: CLITypeResolutionContext

    SYSTEM_BOOLEAN: CLITypeInstance
    SYSTEM_CHAR: CLITypeInstance
    SYSTEM_STRING: CLITypeInstance
    SYSTEM_SINGLE: CLITypeInstance
    SYSTEM_DOUBLE: CLITypeInstance
    SYSTEM_SBYTE: CLITypeInstance
    SYSTEM_INT16: CLITypeInstance
    SYSTEM_INT32: CLITypeInstance
    SYSTEM_INT64: CLITypeInstance
    SYSTEM_UINT64: CLITypeInstance
    SYSTEM_INTPTR: CLITypeInstance
    SYSTEM_UINTPTR: CLITypeInstance
    SYSTEM_BYTE: CLITypeInstance
    SYSTEM_UINT16: CLITypeInstance
    SYSTEM_UINT32: CLITypeInstance
    SYSTEM_OBJECT: CLITypeInstance
    SYSTEM_COLLECTIONS_ARRAYLIST: CLITypeInstance
    SYSTEM_COLLECTIONS_DICTIONARY: CLITypeInstance
    SYSTEM_DATETIME: CLITypeInstance
    SYSTEM_DECIMAL: CLITypeInstance
    SYSTEM_TIMESPAN: CLITypeInstance
    SYSTEM_BYTE_ARRAY: CLITypeInstance

    def from_python_value(self, v: typing.Any) -> CLIValue:
        if v is None:
            return self.SYSTEM_OBJECT.instantiate(None)
        elif isinstance(v, int):
            return self.SYSTEM_INT32.instantiate(v)
        elif isinstance(v, float):
            return self.SYSTEM_DOUBLE.instantiate(v)
        elif isinstance(v, str):
            return self.SYSTEM_STRING.instantiate(v)
        elif isinstance(v, decimal.Decimal):
            return self.SYSTEM_DECIMAL.instantiate(v)
        elif isinstance(v, datetime.datetime):
            return self.SYSTEM_DATETIME.instantiate(v)
        elif isinstance(v, datetime.timedelta):
            return self.SYSTEM_TIMESPAN.instantiate(v)
        elif isinstance(v, bytes):
            return self.SYSTEM_BYTE_ARRAY.instantiate(v)
        else:
            raise TypeError(f"{type(v)} is not a supported type")

    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.SYSTEM_BOOLEAN = CLITypeInstance(ctx, SYSTEM_BOOLEAN, "bool")
        self.SYSTEM_CHAR = CLITypeInstance(ctx, SYSTEM_CHAR, "char")
        self.SYSTEM_STRING = CLITypeInstance(ctx, SYSTEM_STRING, "string")
        self.SYSTEM_SINGLE = CLITypeInstance(ctx, SYSTEM_SINGLE, "float")
        self.SYSTEM_DOUBLE = CLITypeInstance(ctx, SYSTEM_DOUBLE, "double")
        self.SYSTEM_SBYTE = CLITypeInstance(ctx, SYSTEM_SBYTE, "int8")
        self.SYSTEM_INT16 = CLITypeInstance(ctx, SYSTEM_INT16, "int16")
        self.SYSTEM_INT32 = CLITypeInstance(ctx, SYSTEM_INT32, "int32")
        self.SYSTEM_INT64 = CLITypeInstance(ctx, SYSTEM_INT64, "int64")
        self.SYSTEM_INTPTR = CLITypeInstance(ctx, SYSTEM_INTPTR, "IntPtr")
        self.SYSTEM_UINTPTR = CLITypeInstance(ctx, SYSTEM_UINTPTR, "UIntPtr")
        self.SYSTEM_BYTE = CLITypeInstance(ctx, SYSTEM_BYTE, "byte")
        self.SYSTEM_UINT16 = CLITypeInstance(ctx, SYSTEM_UINT16, "uint16")
        self.SYSTEM_UINT32 = CLITypeInstance(ctx, SYSTEM_UINT32, "uint32")
        self.SYSTEM_UINT64 = CLITypeInstance(ctx, SYSTEM_UINT64, "uint64")
        self.SYSTEM_OBJECT = CLITypeInstance(ctx, SYSTEM_OBJECT, "object")
        self.SYSTEM_COLLECTIONS_ARRAYLIST = CLITypeInstance(ctx, SYSTEM_COLLECTIONS_ARRAYLIST)
        self.SYSTEM_COLLECTIONS_DICTIONARY = CLITypeInstance(ctx, SYSTEM_COLLECTIONS_DICTIONARY)
        self.SYSTEM_DATETIME = CLITypeInstance(ctx, SYSTEM_DATETIME)
        self.SYSTEM_DECIMAL = CLITypeInstance(ctx, SYSTEM_DECIMAL)
        self.SYSTEM_TIMESPAN = CLITypeInstance(ctx, SYSTEM_TIMESPAN)
        self.SYSTEM_BYTE_ARRAY = array_of(self.SYSTEM_BYTE)
