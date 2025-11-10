import logging
import shutil
import zipfile
from django.db.models import Model
from io import TextIOWrapper
from contextlib import nullcontext, closing
from typing import Any, Dict, IO, Iterable, List, Optional, Set, Type

from ..policy import ExportPolicy
from ..serializers import Exporter
from ..types import ID, ContainerFormat, Ref, ObjectData
from .._util import UncloseableStream, get_model_options

from .base import BaseContainer
from ._yaml import get_yaml


logger = logging.getLogger('haul.export')


class ExportContainer(BaseContainer):
    '''
    Your starting point for object export.
    '''
    __instance_map: Dict[ID, Any]

    def __init__(
        self,
        exporters: List[Type[Exporter]] = [],
        policy: Optional[ExportPolicy] = None,
        ignore_unknown=False,
    ):
        super().__init__(exporters, ignore_unknown)
        self.__instance_map = {}
        self.policy = policy or ExportPolicy()

    def export_objects(self, objects: Iterable[Model]):
        '''
        Serializes objects and adds them to the container.
        '''
        objects = list(objects)
        if not objects:
            return

        if len(set(ID.kind_for_model(obj) for obj in objects)) > 1:
            raise ValueError('Objects must be of the same class')

        outstanding_refs: Dict[str, Set[ID]] = {}

        model_meta = get_model_options(objects[0].__class__)

        kind = ID.kind_for_model(objects[0])

        objects = [
            instance for instance in objects
            if ID.from_object(instance) not in self.__instance_map and
            self.policy.should_export_object(instance)
        ]

        if not objects:
            return

        exporter_cls = self._exporter_for_model(objects[0])
        exporter = exporter_cls(objects, many=True, context={'export_policy': self.policy})

        logger.debug(f'Exporting {len(objects)} objects of kind {kind}')
        for instance, serialized_data in zip(objects, exporter.data):
            if not instance._meta.pk:
                raise ValueError(f'Cannot export models without a PK')
            pk = serialized_data.pop(instance._meta.pk.name)
            id = ID(kind, pk)
            self.__instance_map[id] = pk
            serialized_obj = ObjectData(id, serialized_data)

            # Collect references
            for key, value in list(serialized_data.items()):
                field_meta = model_meta.get_field(key)

                # Foreign key
                if isinstance(value, ID):
                    if field_meta.null:
                        if not self._should_follow_optional_reference(instance, value, key):
                            serialized_data[key] = None
                            continue

                    outstanding_refs.setdefault(value.kind, set()).add(value)
                    serialized_obj.add_reference(Ref([value], key, nullable=field_meta.null))

                # Reverse foreign key
                if isinstance(value, list) and len(value) and isinstance(value[0], ID):
                    for item in list(value):
                        if field_meta.null:
                            if not self._should_follow_optional_reference(instance, item, key):
                                value.remove(item)
                                continue
                        outstanding_refs.setdefault(item.kind, set()).add(item)
                    serialized_obj.add_reference(Ref(value, key, nullable=field_meta.null))

            # Collect attachments
            serialized_obj.attachments = self.policy.get_attachments(instance) or []

            self._objects[id] = serialized_obj

        for kind, ids in outstanding_refs.items():
            ids = ids - self._objects.keys()
            if ids:
                model_cls = ID.model_for_kind(kind)
                self.export_objects(model_cls.objects.filter(pk__in=[x.pk for x in ids]))

    def _should_follow_optional_reference(self, instance: Model, target: ID, field: str):
        if self.ignore_unknown and not self._exporter_for_kind(target.kind, raise_exception=False):
            logger.debug(f'Ignoring object {target} of unregistered kind')
            return False
        return self.policy.should_follow_reference(instance, target, field)

    def iter_objects(self) -> Iterable[ObjectData]:
        return self._objects.values()

    def write(self, stream: IO[bytes], format: ContainerFormat = ContainerFormat.YAML, metadata: Any = None):
        '''
        Writes the serialized objects from the container into a data stream.

        :param stream: The stream to write into. For ``ContainerFormat.ZIP_*``, has to be seekable.
        :param metadata: a free-form metadata object that will be stored in the stream. It's available later through :attr:`ImportContainer.metadata`.
        '''
        for item in self._write(stream, format, metadata):
            if isinstance(item, Exception):
                raise item

    def _write(self, stream: IO[bytes], format: ContainerFormat = ContainerFormat.YAML, metadata: Any = None):
        stream = UncloseableStream(stream)
        if format == ContainerFormat.YAML:
            for obj in self._objects.values():
                if len(obj.attachments):
                    raise ValueError('File attachments require a ZIP based container format')

            archive = nullcontext()
            metadata_stream = TextIOWrapper(stream)  # type: ignore
        else:
            archive = zipfile.ZipFile(
                stream,
                mode='w',
                compression=zipfile.ZIP_STORED if format == ContainerFormat.NON_COMPRESSED_ZIP else zipfile.ZIP_DEFLATED,
            )
            metadata_stream = TextIOWrapper(archive.open('metadata.yaml', 'w'))

        with archive:
            with metadata_stream:
                yaml = get_yaml()
                header = {
                    '_': 'header',
                    'version': 1,
                    'object_kinds': list(set(x.kind for x in self._objects.keys())),
                    'metadata': metadata,
                }
                metadata_stream.write('\n---\n')
                yaml.dump(header, metadata_stream)
                for obj in self._objects.values():
                    data = {
                        '_': 'object',
                        'id': obj.id,
                        'data': obj.serialized_data,
                        'attachments': obj.attachments,
                    }
                    data = (yield (data, obj)) or data

                    metadata_stream.write('\n---\n')
                    try:
                        yaml.dump(data, metadata_stream)
                    except Exception as exc:
                        yield exc

            for obj in self._objects.values():
                for attachment in obj.attachments:
                    if not archive:
                        raise ValueError('Attachments specified not container format is not a ZIP')
                    with archive.open(f'attachments/{attachment.id}', 'w') as output:
                        assert attachment.content_provider is not None
                        attachment_stream = attachment.content_provider()
                        with closing(attachment_stream):
                            shutil.copyfileobj(attachment_stream, output)  # type: ignore
