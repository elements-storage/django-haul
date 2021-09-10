from haul import ForeignKey, ReverseForeignKey, Exporter, ManyToMany
from .models import Book, Author, Tag


class TagExporter(Exporter):
    class Meta:
        fields = '__all__'
        model = Tag


class BookExporter(Exporter):
    author = ForeignKey()
    coauthor = ForeignKey(allow_null=True)
    tags = ManyToMany()

    class Meta:
        fields = '__all__'
        model = Book


class AuthorExporter(Exporter):
    books = ReverseForeignKey()
    tags = ManyToMany()

    class Meta:
        fields = '__all__'
        model = Author
