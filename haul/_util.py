from django.db.models.base import Model
from django.db.models.options import Options
from typing import Type


class UncloseableStream:
    def __init__(self, stream):
        self._stream = stream

    # Prevents ZipFile from closing the stream
    def __getattribute__(self, name: str):
        if name == 'close':
            return lambda: None
        return getattr(object.__getattribute__(self, '_stream'), name)


def get_model_options(model_cls: Type[Model]) -> Options:
    _cm = model_cls._meta.concrete_model
    if not _cm:
        raise RuntimeError(f'No concrete model for {model_cls}')
    return _cm._meta
