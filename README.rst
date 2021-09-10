.. image:: https://i.imgur.com/ARniMyK.png

.. image:: https://img.shields.io/pypi/v/django-haul.svg
    :target: https://pypi.python.org/pypi/django-haul

.. image:: https://readthedocs.org/projects/haul/badge/?version=latest
    :target: https://haul.readthedocs.io/en/latest/?version=latest
    :alt: Documentation Status

Object graph import/export framework for Django

* Free software: MIT license
* Documentation: https://haul.readthedocs.io.
* Experimental: active in production, but the API is subject to change.

About
-----

Haul allows you to add model export/import functionality to your Django app.
It can export some or all objects out of the Django ORM, store them in a file or a stream, and later import them back into the same or a *different* database / application instance.

When importing into a different database, you can customize how the imported objects are mapped against existing objects in the DB, and define what gets overwritten and what gets created anew.


Features
--------

* Automatically follows FK and M2M references
* Flexible serialization behaviours
* Flexible object relinking on import
* File attachments support
* Compressed and plaintext formats

Installation
------------

::

    pip install django-haul


Example
-------

Consider following models:

.. code-block:: python

    from django.db import models


    class Tag(models.Model):
        name = models.CharField(max_length=32)

    class Author(models.Model):
        name = models.CharField(max_length=100)
        tags = models.ManyToManyField(Tag)

    class Book(models.Model):
        author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name='books')
        coauthor = models.ForeignKey(Author, on_delete=models.SET_NULL, null=True)
        name = models.CharField(max_length=100)
        isbn = models.CharField(max_length=100, null=True)
        tags = models.ManyToManyField(Tag)


To expose models to Haul, you need to define ``Exporter`` classes:

.. code-block:: python

    from haul import Exporter, ForeignKey, ReverseForeignKey, ManyToMany

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

``Exporter`` base class is based on Django REST Framework's own ``ModelSerializer`` and will auto-discover non-relational fields.

Now, to export all books into a file, you can use:

.. code-block:: python

    EXPORTERS = [BookExporter, AuthorExporter, TagExporter]

    with open('export.haul', 'wb') as f:
        c = ExportContainer(exporters=EXPORTERS)
        c.export_objects(Book.objects.all())
        c.write(f)

The output file will contain an object graph dump:

.. code-block:: yaml

    ---
    _: header
    metadata: null
    object_kinds:
    - test_app:book
    - test_app:author
    version: 1

    ---
    _: object
    attachments: []
    data: !!omap
    - books:
    - !<ID>
        kind: test_app:book
        pk: 1
    - tags: []
    - name: '1'
    id: !<ID>
    kind: test_app:author
    pk: 1

    ---
    _: object
    attachments: []
    data: !!omap
    - books: []
    - tags: []
    - name: '2'
    id: !<ID>
    kind: test_app:author
    pk: 2

    ---
    _: object
    attachments: []
    data: !!omap
    - author: !<ID>
        kind: test_app:author
        pk: 1
    - coauthor: null
    - tags: []
    - name: b1
    - isbn: null
    id: !<ID>
    kind: test_app:book
    pk: 1

You can also inspect the objects within the files with the CLI dump tool::

    python -m haul.cli export.haul

Note how the ``Author`` objects related to the ``Book`` instances got picked up and exported automatically.

To import this data back into the database, you can simply feed it to an ``ImportContainer``:

.. code-block:: python

    from haul import ImportContainer

    c = ImportContainer(exporters=EXPORTERS)
    with open('export.haul', 'rb') as f:
        with c.read(f):
            c.import_objects()

This, however, will unconditionally create new objects, even if books and authors with the same names already exist.

You can flexibly define how Haul should treat existing and duplicate objects. For example, let's prevent duplicate authors from being imported, but keep duplicate books and link them to the already existing authors:

.. code-block:: python

    from haul import ImportPolicy, RelinkAction

    class BookImportPolicy(ImportPolicy):
        def relink_object(self, model_cls, obj):
            if model_cls is Book:
                # Unconditionally import as a new object
                return RelinkAction.Create()

            if model_cls is Author:
                return RelinkAction.LinkByFields(
                    # Look up authors by their names
                    lookup_fields=('name',),
                    # Fall back to creation if not found
                    fallback=RelinkAction.Create(),
                )

            # Do not import other object types
            return RelinkAction.Discard()

    c = ImportContainer(exporters=EXPORTERS, policy=BookImportPolicy())
    with open('export.haul', 'rb') as f:
        with c.read(d):
            c.import_objects()

See :mod:`haul.policy` for other relink actions.
