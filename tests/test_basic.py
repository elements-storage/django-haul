from haul.policy import ImportPolicy, RelinkAction
from io import BytesIO
from test_app.app import reset
from test_app.models import Book, Author, Tag
from test_app.export import BookExporter, AuthorExporter, TagExporter

from haul import ImportContainer, ExportContainer


EXPORTERS = [BookExporter, AuthorExporter, TagExporter]


def test_simple_roundtrip():
    reset()
    Author.objects.create(name='1')
    Author.objects.create(name='2')

    d = BytesIO()

    c = ExportContainer(exporters=EXPORTERS)
    c.export_objects(Author.objects.all())
    c.write(d)

    reset()

    c = ImportContainer(exporters=EXPORTERS)
    with c.read(d):
        c.import_objects()

    assert Author.objects.count() == 2
    assert Author.objects.order_by('name').first().name == '1'
    assert Author.objects.order_by('name').last().name == '2'


def test_fk():
    reset()
    a1 = Author.objects.create(name='1')
    Author.objects.create(name='2')
    Book.objects.create(name='b1', author=a1)

    d = BytesIO()

    c = ExportContainer(exporters=EXPORTERS)
    c.export_objects(Author.objects.all())
    c.export_objects(Book.objects.all())
    c.write(d)

    reset()

    c = ImportContainer(exporters=EXPORTERS)
    with c.read(d):
        c.import_objects()

    assert Author.objects.count() == 2
    assert Book.objects.count() == 1
    assert Book.objects.first().author == Author.objects.get(name='1')
