from haul import ContainerFormat, Attachment, ExportContainer, ExportPolicy
from test_app.models import Book, Author, Tag
from test_app.export import BookExporter, AuthorExporter, TagExporter

Tag.objects.bulk_create([Tag(name='T1'), Tag(name='T2'), Tag(name='T3')])
tags = Tag.objects.all()
a1 = Author.objects.create(name='1')
a1.tags.set([tags[0]])
a2 = Author.objects.create(name='2')
a2.tags.set([tags[0], tags[1]])
Book.objects.create(name='A', author=a1)
Book.objects.create(name='B', author=a1).tags.set([tags[1], tags[2]])
Book.objects.create(name='C', author=a2)

class EP(ExportPolicy):
    def get_attachments(self, instance):
        if isinstance(instance, Book):
            return [Attachment.from_data(key='book', data=b'content for %s' % str(instance).encode())]


c = ExportContainer(policy=EP())
c.register_exporter(BookExporter)
c.register_exporter(AuthorExporter)
c.register_exporter(TagExporter)
c.export_objects(Author.objects.all())

c.dump_objects()

with open('export/export.zip', 'wb') as f:
    c.write(f, format=ContainerFormat.COMPRESSED_ZIP)
