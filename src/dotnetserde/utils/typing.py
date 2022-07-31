import typing
from collections.abc import Collection, Iterator

T = typing.TypeVar("T")


def iterable_move(i: typing.Iterable[T]) -> typing.Iterable[T]:
    if isinstance(i, Iterator):
        return list(i)
    else:
        return i


def collection_move(i: typing.Iterable[T]) -> typing.Collection[T]:
    if isinstance(i, Collection):
        return i
    else:
        return list(i)


def raise_exception(f: typing.Callable[[], BaseException]) -> T:
    raise f()
