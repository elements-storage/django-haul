'''
A nifty CLI tool to dump an exported file's contents for debugging.

Call it like this::

    python -m haul.cli /path/to/file.haul
'''

import argparse
import django
from django.conf import settings
from . import ImportContainer


def main():
    parser = argparse.ArgumentParser(description='Haul CLI')
    parser.add_argument('path', type=str)
    args = parser.parse_args()
    container = ImportContainer(ignore_unknown=True)

    settings.configure()
    django.setup()

    with open(args.path, 'rb') as f:
        with container.read(f):
            container.dump_objects()


if __name__ == '__main__':
    main()
