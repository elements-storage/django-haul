import io
import uuid
from dataclasses import dataclass, field, asdict
from django.apps import registry
from django.db.models import Model
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Type, BinaryIO, Union
from uuid import uuid4


class ContainerFormat(Enum):
    YAML = auto()
    COMPRESSED_ZIP = auto()
    NON_COMPRESSED_ZIP = auto()


@dataclass(frozen=True)
class ID:
    kind: str
    pk: Any

    yaml_tag = 'ID'

    def __str__(self):
        return f'{self.kind}-{self.pk}'

    @classmethod
    def from_object(cls, obj: Model) -> 'ID':
        pk = obj.pk
        if isinstance(pk, uuid.UUID):
            pk = str(pk)
        return ID(ID.kind_for_model(obj), pk)

    @staticmethod
    def kind_for_model(obj: Union[Model, Type[Model]]):
        return f'{obj._meta.app_label}:{obj._meta.model_name}'

    @staticmethod
    def model_for_kind(kind: str) -> Type[Model]:
        app_label, name, *_ = kind.split(':')
        return registry.apps.get_model(app_label, name)

    def serialize(self):
        d = asdict(self)
        if isinstance(self.pk, uuid.UUID):
            d['pk'] = str(d['pk'])
        return d

    @classmethod
    def to_yaml(cls, representer, node):
        return representer.represent_mapping('ID', node.serialize())

    @classmethod
    def deserialize(cls, s: Any) -> 'ID':
        if not isinstance(s, dict):
            raise ValueError(f'Value must be a dict, not {s}')
        return ID(**s)

    @classmethod
    def from_yaml(cls, loader, node):
        return ID(**loader.construct_mapping(node, deep=True))


@dataclass(frozen=True)
class Ref:
    ids: List[ID]
    field: str
    nullable: bool = False
    weak: bool = False


@dataclass
class Attachment:
    id: str
    key: Any
    content_provider: Optional[Callable[[], BinaryIO]] = None
    _container_stream: Optional[BinaryIO] = None

    @classmethod
    def from_path(cls, key: Any, path: str):
        return cls(
            id=str(uuid4()),
            key=key,
            content_provider=lambda: io.FileIO(path, 'rb'),
        )

    @classmethod
    def from_data(cls, key: Any, data: bytes):
        return cls(
            id=str(uuid4()),
            key=key,
            content_provider=lambda: io.BytesIO(data),  # type: ignore
        )

    @classmethod
    def to_yaml(cls, representer, node):
        data = asdict(node)
        data.pop('content_provider')
        return representer.represent_dict(data)


@dataclass
class ObjectData:
    id: ID
    serialized_data: Dict[str, Any]
    fields: Optional[Dict[str, Any]] = None
    refs: List[Ref] = field(default_factory=list)
    refers_to: Set[ID] = field(default_factory=set)
    attachments: List[Attachment] = field(default_factory=list)

    def add_reference(self, ref: Ref):
        self.refs.append(ref)
        self.refers_to |= set(ref.ids)

    def __hash__(self) -> int:
        return hash(self.id)
