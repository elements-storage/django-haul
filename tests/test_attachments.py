from haul.types import ContainerFormat
from unittest import mock
from haul import ExportPolicy, ImportPolicy, RelinkAction, Attachment
from io import BytesIO
from test_app.app import reset
from test_app.models import Book, Author, Tag
from test_app.export import BookExporter, AuthorExporter, TagExporter

from haul import ImportContainer, ExportContainer


EXPORTERS = [BookExporter, AuthorExporter, TagExporter]


def test_attachments():
    reset()
    a1 = Author.objects.create(name='1')
    b1 = Book.objects.create(name='b1', author=a1)

    class EPolicy(ExportPolicy):
        def get_attachments(self, instance):
            print(instance)
            if instance == b1:
                return [Attachment.from_data('content', b'text')]
            return []

    d = BytesIO()

    c = ExportContainer(exporters=EXPORTERS, policy=EPolicy())
    c.export_objects(Book.objects.all())
    c.write(d, format=ContainerFormat.COMPRESSED_ZIP)

    reset()

    class IPolicy(ImportPolicy):
        def process_attachment(self, instance, key, stream):
            self.file_content = stream.read()

    ipolicy = IPolicy()
    ipolicy.process_attachment = mock.Mock(wraps=ipolicy.process_attachment)

    c = ImportContainer(exporters=EXPORTERS, policy=ipolicy)
    with c.read(d):
        c.import_objects()

        assert len(ipolicy.process_attachment.call_args_list) == 1
        assert ipolicy.process_attachment.call_args_list[0][0][0] == Book.objects.first()
        assert ipolicy.process_attachment.call_args_list[0][0][1] == 'content'
        assert ipolicy.file_content == b'text'
