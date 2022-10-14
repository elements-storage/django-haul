#!/usr/bin/env python

"""The setup script."""

from setuptools import setup, find_packages

with open('README.rst') as readme_file:
    readme = readme_file.read()

requirements = [
    'django>=3',
    'djangorestframework>=3',
    'ruamel.yaml>=0.17',
    'graphlib-backport; python_version<"3.9"',
]

test_requirements = ['pytest>=3', 'typing_extensions']

setup(
    author="Eugene Pankov`",
    author_email='e.pankov@elements.tv',
    python_requires='>=3.7',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
    ],
    description="Structured object import/export for Django ORM",
    install_requires=requirements,
    license="MIT",
    long_description=readme,
    long_description_content_type='text/markdown',
    include_package_data=True,
    keywords=['django', 'orm', 'export', 'import'],
    name='django-haul',
    packages=find_packages(include=['haul', 'haul.*']),
    test_suite='tests',
    tests_require=test_requirements,
    url='https://github.com/elements-storage/haul',
    version='0.0.11',
    zip_safe=False,
)
