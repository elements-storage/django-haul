import graphlib
import logging
import zipfile
from contextlib import contextmanager
from django.apps.registry import apps
from django.db.models import ManyToOneRel, Model
from io import TextIOWrapper, BufferedReader
from typing import Any, BinaryIO, Dict, Iterable, List, Optional, Set, Tuple, Type

from ..errors import ModelClassNotRegistered
from ..policy import ImportPolicy
from ..serializers import Exporter
from ..types import ID, Ref, ObjectData, Attachment
from .._util import UncloseableStream, get_model_options

from .base import BaseContainer
from ._yaml import get_yaml


logger = logging.getLogger('haul.import')


class ImportReport:
    loaded_objects: Set[ObjectData]
    imported_objects: Set[Model]
    discarded_objects: Set[ObjectData]
    pk_map: Dict[ID, Model]

    def __init__(self):
        self.loaded_objects = set()
        self.imported_objects = set()
        self.discarded_objects = set()
        self.pk_map = {}


class ImportContainer(BaseContainer):
    '''
    Your starting point for object import.
    '''
    __instance_map: Dict[ID, Model]
    __discarded_objects: Set[ID]

    #: free-form metadata as stored by :func:`ExportContainer.write`
    metadata: Any = None

    def __init__(
        self,
        exporters: List[Type[Exporter]] = [],
        policy: Optional[ImportPolicy] = None,
        ignore_unknown=False,
    ):
        super().__init__(exporters, ignore_unknown)
        self.__instance_map = {}
        self.__discarded_objects = set()
        self.__open = False
        self.policy = policy or ImportPolicy()
        self.report = ImportReport()

    @contextmanager
    def read(self, stream: BinaryIO):
        '''
        Reads a data stream, deserializes objects in it and stores them inside the container.

        This is a context manager which has to be kept open when :func:`import_objects` is called::

            c = ImportContainer(exporters=...)
            with open(...) as f:
                with c.read(f):
                    c.import_objects()
        '''
        stream.seek(0)
        stream = UncloseableStream(stream)
        reader = BufferedReader(stream)  # type: ignore
        signature = reader.peek(4)

        archive: Optional[zipfile.ZipFile] = None
        if signature[:2] == b'PK':
            logger.debug('Detected a ZIP container')
            archive = zipfile.ZipFile(reader, 'r')
            try:
                metadata_stream = archive.open('metadata.yaml', 'r')
            finally:
                archive.close()
        else:
            metadata_stream = reader

        try:
            try:
                all_kinds = set(ID.kind_for_model(x) for x in apps.get_models())
                yaml = get_yaml()
                for document in yaml.load_all(TextIOWrapper(metadata_stream)):
                    if document['_'] == 'header':
                        if document['version'] != 1:
                            raise ValueError(f'Unknown container version {document["version"]}')
                        unknown_kinds = set(document['object_kinds']) - all_kinds
                        if unknown_kinds and not self.ignore_unknown:
                            raise ValueError(f'Unknown object types {unknown_kinds}')
                        self.metadata = document.get('metadata')
                        if self.metadata:
                            logger.debug(f'Container metadata: {self.metadata}')
                    elif document['_'] == 'object':
                        id = document['id']
                        logger.debug(f'Extracting object {id}')
                        obj = ObjectData(
                            id=document['id'],
                            serialized_data=document['data'],
                            attachments=[
                                Attachment(
                                    id=item['id'],
                                    key=item['key'],
                                    _container_stream=stream,  # type: ignore
                                )
                                for item in document['attachments']
                            ]
                        )
                        if obj.id in self._objects:
                            raise ValueError(f'Duplicate object {obj.id} found')
                        self._objects[obj.id] = obj
                        self.report.loaded_objects.add(obj)
                    else:
                        raise ValueError(f'Unknown container segment "{document["_"]}"')
            finally:
                metadata_stream.close()

            try:
                self.__open = True
                yield
            finally:
                self.__open = False

        finally:
            if archive:
                archive.close()

    def _register_imported(self, obj: ObjectData, instance: Model):
        logger.debug(f'Imported {instance}')
        self.report.imported_objects.add(instance)
        self.__instance_map[obj.id] = instance

    def _discard_objects(self, objects: Iterable[ObjectData], reason=None):
        for kind, objects in self.__group_by_kind(objects).items():
            if len(objects) <= 5:
                description = ', '.join(str(x) for x in objects)
            else:
                description = f'{len(objects)} {kind} objects'
            logger.debug(f'Discarding {description} {reason or ""}')
            self.__discarded_objects |= {x.id for x in objects}
            self.report.discarded_objects |= set(objects)

    def import_objects(self) -> ImportReport:
        '''
        Untangles the object graph, relinks objects and imports them into the database.
        '''
        if not self.__open:
            raise RuntimeError('Container is not open - open a .read() context first')

        kind_map = self.__group_by_kind(self._objects.values())

        # ----------------
        # Deserialize data

        for kind, objects in list(kind_map.items()):
            try:
                exporter_cls = self._exporter_for_kind(kind)
            except ModelClassNotRegistered:
                if self.ignore_unknown:
                    self._discard_objects(objects, reason='due to unknown type')
                    continue
                raise

            exporter = exporter_cls(data=[x.serialized_data for x in objects], many=True)
            exporter.is_valid(raise_exception=True)
            logger.debug(f'Deserialized {len(objects)} {kind} objects')

            if len(objects) != len(exporter.validated_data):
                raise ValueError('Serializer has failed to deserialize all objects')

            for obj, deserialized_data in zip(objects, exporter.validated_data):
                obj.fields = deserialized_data
                assert obj.fields is not None
                for key, value in obj.fields.items():
                    # Foreign key
                    if isinstance(value, Ref):
                        obj.add_reference(value)
                        if len(value.ids):
                            logger.debug(f'Found a reference from {obj.id} to {value.ids}')

            for obj in self._objects.values():
                for ref in obj.refs:
                    for id in ref.ids:
                        if id not in self._objects:
                            raise ValueError(f'Unresolved reference to {id} from {obj.id} via {ref.field}')

        # -------------------
        # Build object graph

        sorter: graphlib.TopologicalSorter[ObjectData] = graphlib.TopologicalSorter(None)
        for obj in self._objects.values():
            if obj.id not in self.__discarded_objects:
                deps = [
                    self._objects[id]
                    for ref in obj.refs
                    for id in ref.ids
                    if id not in self.__discarded_objects and not ref.weak
                ]
                sorter.add(
                    obj,
                    *deps,
                )

        try:
            sorter.prepare()
        except graphlib.CycleError as e:
            logger.error('Cycle detected')
            for obj in e.args[1]:
                logger.error(f' - {obj}')
            raise e

        while sorter.is_active():
            ready_objects: Tuple[ObjectData, ...] = sorter.get_ready()
            if not len(ready_objects):
                raise RuntimeError('Could not untangle the reference graph')

            kind_map = self.__group_by_kind(ready_objects)

            # -------------------
            # Resolve all references

            for kind, objects in kind_map.items():
                model_meta = get_model_options(ID.model_for_kind(kind))

                for obj in objects:
                    assert obj.fields is not None
                    for ref in obj.refs:
                        if ref.weak:
                            continue
                        remaining_ids = list(ref.ids)
                        discarded = False

                        for id in ref.ids:
                            if id not in self.__instance_map:
                                if id in self.__discarded_objects:
                                    if ref.nullable:
                                        logger.debug(f'Breaking reference {obj.id}.{ref.field} due to target object being discarded')
                                        remaining_ids.remove(id)
                                        continue
                                    else:
                                        self._discard_objects([obj], reason=f'due to a broken reference via {ref.field}')
                                        sorter.done(obj)
                                        discarded = True
                                        break
                                raise ValueError(f'Consistency error: PK still unknown for {id} (referenced by {obj.id} via {ref.field})')

                        if discarded:
                            continue

                        if model_meta.get_field(ref.field).many_to_many:
                            obj.fields[ref.field] = [
                                self.__instance_map[id]
                                for id in remaining_ids
                            ]
                            if len(remaining_ids):
                                logger.debug(f'Remapped M2M {obj.id}.{ref.field} reference from {ref.ids} to {obj.fields[ref.field]}')
                        else:
                            if len(remaining_ids):
                                obj.fields[ref.field] = self.__instance_map[remaining_ids[0]]
                                logger.debug(f'Remapped {obj.id}.{ref.field} reference from {ref.ids[0]} to {obj.fields[ref.field].pk}')
                            else:
                                obj.fields[ref.field] = None

                    # Remove reverse FK fields
                    for relation in model_meta.related_objects:
                        if isinstance(relation, ManyToOneRel) and relation.related_name:
                            obj.fields.pop(relation.related_name, None)

                # -------------------
                # Gather relink actions

                for obj in objects:
                    assert obj.fields is not None
                    self.policy.preprocess_object_fields(ID.model_for_kind(kind), obj.fields)

                relink_actions = [
                    self.policy.relink_object(
                        ID.model_for_kind(kind),
                        obj,
                    )
                    for obj in objects
                    if obj.id not in self.__discarded_objects
                ]

                # -------------------
                # Execute relink actions

                for action in set(relink_actions):
                    action_objects = [x[1] for x in zip(relink_actions, objects) if x[0] == action]

                    for obj in action_objects:
                        assert obj.fields is not None
                        self.policy.postprocess_object_fields(ID.model_for_kind(kind), obj.fields)

                    logger.debug(f'Running {action} on {len(action_objects)} {kind} objects')
                    instances = action._execute(ID.model_for_kind(kind), action_objects, self.policy)
                    for obj, instance in zip(action_objects, instances):
                        if instance is False:
                            self._discard_objects([obj], reason='due to relink policy')
                        else:
                            self.policy.post_object_import(instance)
                            self._register_imported(obj, instance)
                        sorter.done(obj)

        # -------------------
        # Process attachments

        container_streams = set()
        for obj in self._objects.values():
            for attachment in obj.attachments:
                if not attachment._container_stream:
                    raise RuntimeError(f'Container stream not set for attachment {attachment}')
                container_streams.add(attachment._container_stream)

        for stream in container_streams:
            with zipfile.ZipFile(stream, 'r') as zfile:
                for obj in self._objects.values():
                    if obj.id in self.__discarded_objects:
                        continue
                    for attachment in obj.attachments:
                        if attachment._container_stream == stream:
                            with zfile.open(f'attachments/{attachment.id}', 'r') as f:
                                self.policy.process_attachment(self.__instance_map[obj.id], attachment.key, f)

        self.report.pk_map = self.__instance_map
        return self.report

    def __group_by_kind(self, objects: Iterable[ObjectData]) -> Dict[str, List[ObjectData]]:
        kind_map: Dict[str, List[ObjectData]] = {}
        for obj in objects:
            kind_map.setdefault(obj.id.kind, []).append(obj)
        return kind_map
