import django
from django.db import connections
import os
from django.conf import settings
from django.core.management import call_command
from pathlib import Path


def setup():
    if setup._configured:
        return
    setup._configured = True
    settings.configure(
        DATABASES={
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': str(Path(os.getcwd()) / 'db.sqlite'),
            },
        },
        INSTALLED_APPS=[
            'test_app',
        ],
        SECRET_KEY='test',
    )
    django.setup()


def reset():
    connections.close_all()

    try:
        os.unlink('db.sqlite')
    except FileNotFoundError:
        pass

    setup()
    call_command('migrate', '--run-syncdb', interactive=False)


setattr(setup, '_configured', False)
