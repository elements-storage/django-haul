from haul.policy import ImportPolicy, RelinkAction
from io import BytesIO
from test_app.app import reset
from test_app.models import Book, Author, Tag
from test_app.export import BookExporter, AuthorExporter, TagExporter

from haul import ImportContainer, ExportContainer


EXPORTERS = [BookExporter, AuthorExporter, TagExporter]


def test_discard_chain():
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

    class Policy(ImportPolicy):
        def relink_object(self, model_cls, obj):
            if model_cls is Author and obj.fields['name'] == '1':
                return RelinkAction.Discard()
            return RelinkAction.Create()

    c = ImportContainer(exporters=EXPORTERS, policy=Policy())
    with c.read(d):
        c.import_objects()

    assert not Author.objects.filter(name='1').exists()
    assert Author.objects.filter(name='2').exists()
    assert Book.objects.count() == 0


def test_discard_optional():
    reset()
    a1 = Author.objects.create(name='1')
    a2 = Author.objects.create(name='2')
    Book.objects.create(name='b1', author=a1, coauthor=a2)

    d = BytesIO()

    c = ExportContainer(exporters=EXPORTERS)
    c.export_objects(Book.objects.all())
    c.write(d)

    reset()

    class Policy(ImportPolicy):
        def relink_object(self, model_cls, obj):
            if model_cls is Author and obj.fields['name'] == '2':
                return RelinkAction.Discard()
            return RelinkAction.Create()

    c = ImportContainer(exporters=EXPORTERS, policy=Policy())
    with c.read(d):
        c.import_objects()

    assert Author.objects.count() == 1
    assert Book.objects.count() == 1
    assert Book.objects.first().coauthor is None


def test_relink_fields():
    reset()
    a1 = Author.objects.create(name='1')
    Author.objects.create(name='2')
    Book.objects.create(name='b1', author=a1)

    d = BytesIO()

    c = ExportContainer(exporters=EXPORTERS)
    c.export_objects(Author.objects.all())
    c.export_objects(Book.objects.all())
    c.write(d)

    Book.objects.all().delete()
    Author.objects.filter(name='2').delete()

    class Policy(ImportPolicy):
        def relink_object(self, model_cls, obj):
            if model_cls is Author:
                return RelinkAction.LinkByFields(
                    lookup_fields=('name',),
                    fallback=RelinkAction.Create(),
                )
            return RelinkAction.Create()

    c = ImportContainer(exporters=EXPORTERS, policy=Policy())
    with c.read(d):
        c.import_objects()

    assert Author.objects.count() == 2
    assert Book.objects.count() == 1
    assert Book.objects.first().author == Author.objects.get(name='1')


def test_relink_and_overwrite_fields():
    reset()
    a = Author.objects.create(name='a')
    Book.objects.create(name='b1', isbn='101', author=a)
    Book.objects.create(name='b2', isbn='102', author=a)

    d = BytesIO()

    c = ExportContainer(exporters=EXPORTERS)
    c.export_objects(Book.objects.all())
    c.write(d)

    Book.objects.filter(name='b2').update(name='updated')

    class Policy(ImportPolicy):
        def relink_object(self, model_cls, obj):
            if model_cls is Book:
                return RelinkAction.LinkByFields(
                    lookup_fields=('isbn',),
                    overwrite_fields=('name',),
                )
            if model_cls is Author:
                return RelinkAction.LinkByFields(lookup_fields=('name',))

    c = ImportContainer(exporters=EXPORTERS, policy=Policy())
    with c.read(d):
        c.import_objects()

    assert Book.objects.count() == 2
    assert Book.objects.filter(name='b2').exists()
    assert not Book.objects.filter(name='updated').exists()


def test_relink_by_pk():
    reset()
    a = Author.objects.create(name='a')
    Book.objects.create(name='b1', author=a)
    Book.objects.create(name='b2', author=a)

    d = BytesIO()

    c = ExportContainer(exporters=EXPORTERS)
    c.export_objects(Book.objects.all())
    c.write(d)

    Book.objects.filter(name='b2').update(name='updated')

    class Policy(ImportPolicy):
        def relink_object(self, model_cls, obj):
            return RelinkAction.LinkByPK()

    c = ImportContainer(exporters=EXPORTERS, policy=Policy())
    with c.read(d):
        c.import_objects()

    assert Author.objects.count() == 1
    assert Book.objects.count() == 2
    assert Book.objects.filter(name='updated').exists()


def test_relink_to_instance():
    reset()
    a = Author.objects.create(name='a')
    Book.objects.create(name='b1', author=a)
    Book.objects.create(name='b2', author=a)

    d = BytesIO()

    c = ExportContainer(exporters=EXPORTERS)
    c.export_objects(Book.objects.all())
    c.write(d)

    imp_a = Author.objects.create(name='imported books author')

    class Policy(ImportPolicy):
        def relink_object(self, model_cls, obj):
            if model_cls is Author:
                return RelinkAction.LinkToInstance(pk=imp_a.pk)
            return RelinkAction.Create()

    c = ImportContainer(exporters=EXPORTERS, policy=Policy())
    with c.read(d):
        c.import_objects()

    assert Author.objects.count() == 2
    assert Book.objects.count() == 4
    assert imp_a.books.count() == 2
