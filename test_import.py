from haul.policy import ImportPolicy, RelinkAction
from haul.containers import ImportContainer
from test_app.models import Book, Author
from test_app.export import BookExporter, AuthorExporter, TagExporter

class IP(ImportPolicy):
    def relink_object(self, model_cls, obj):
        if model_cls == Author:
            return RelinkAction.LinkByFields(
                lookup_fields=('name',),
                fallback=RelinkAction.Create()
            )
        return RelinkAction.Create()

    def process_attachment(self, instance, key, stream):
        print(instance, key, stream.read())

a1 = Author.objects.create(name='1')
a3 = Author.objects.create(name='3')

c = ImportContainer(policy=IP())
c.register_exporter(BookExporter)
c.register_exporter(AuthorExporter)
c.register_exporter(TagExporter)

with open('export/export.zip', 'rb') as f:
    with c.read(f):
        c.import_objects()

print(Author.objects.all())
print(Book.objects.all())
