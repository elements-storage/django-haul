from haul.policy import ImportPolicy, RelinkAction
from io import BytesIO
from test_app.app import reset
from test_app.models import Book, Author, Tag
from test_app.export import BookExporter, AuthorExporter, TagExporter

from haul import ImportContainer, ExportContainer


EXPORTERS = [BookExporter, AuthorExporter, TagExporter]


def test_report_discard():
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
        report = c.import_objects()

    assert report.imported_objects == set(Author.objects.all())
    assert len(report.discarded_objects) == 2
    assert {x.fields['name'] for x in report.discarded_objects} == {'1', 'b1'}

    obj_author = next(x for x in report.loaded_objects if x.fields['name'] == '2')
    assert report.pk_map[obj_author.id] == Author.objects.get(name='2')
