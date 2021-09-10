from django.db import models


class Tag(models.Model):
    name = models.CharField(max_length=32)

    def __str__(self):
        return f'[Tag {self.name}]'


class Author(models.Model):
    name = models.CharField(max_length=100)
    tags = models.ManyToManyField(Tag)

    def __str__(self):
        return f'[Author {self.name}]'


class Book(models.Model):
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name='books')
    coauthor = models.ForeignKey(Author, on_delete=models.SET_NULL, null=True)
    name = models.CharField(max_length=100)
    isbn = models.CharField(max_length=100, null=True)
    tags = models.ManyToManyField(Tag)

    def __str__(self):
        return f'[Book {self.name} by {self.author}]'
