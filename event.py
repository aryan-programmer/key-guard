from collections.abc import Callable
from types import EllipsisType
from typing import Generic, List, TypeVar, Union


TOrigin = TypeVar("TOrigin")
TParameter = TypeVar("TParameter")


class Event(Generic[TOrigin, TParameter]):
    _listeners: List[Callable[[TOrigin, TParameter], None]]

    def __init__(self, origin: TOrigin):
        self._origin = origin
        # Initialise a list of listeners
        self._listeners = []

    # Define a getter for the 'on' property which returns the decorator.
    @property
    def on(self):
        # A decorator to run addListener on the input function.
        def wrapper(
            func: Callable[[TOrigin, TParameter], None]
        ) -> Callable[[TOrigin, TParameter], None]:
            self.add_listener(func)
            return func

        return wrapper

    # Add and remove functions from the list of listeners.
    def add_listener(self, func: Callable[[TOrigin, TParameter], None]):
        if func in self._listeners:
            return
        self._listeners.append(func)

    def remove_listener(self, func: Callable[[TOrigin, TParameter], None]):
        if func not in self._listeners:
            return
        self._listeners.remove(func)

    # Trigger events.
    def trigger(self, parameter: Union[TParameter, EllipsisType] = ...):
        if parameter is ...:
            for func in self._listeners:
                func(self._origin)
        else:
            for func in self._listeners:
                func(self._origin, parameter)
