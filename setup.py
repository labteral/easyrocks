#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import find_packages
from setuptools import setup
from pathlib import Path


ROOT = Path(__file__).parent
version_namespace = {}
exec(
    (ROOT / 'easyrocks' / '_version.py').read_text(),
    version_namespace,
)

setup(name='easyrocks',
      version=version_namespace['__version__'],
      description='Work easier with RocksDB in Python',
      long_description='Work easier with RocksDB in Python.',
      long_description_content_type='text/plain',
      url='https://github.com/brunneis/easyrocks',
      project_urls={
          'Source': 'https://github.com/brunneis/easyrocks',
          'Issues': 'https://github.com/brunneis/easyrocks/issues',
      },
      author='Rodrigo Martínez Castaño',
      author_email='rodrigo@martinez.gal',
      license_expression='GPL-3.0-only',
      packages=find_packages(),
      zip_safe=False,
      classifiers=[
          "Development Status :: 4 - Beta",
          "Environment :: Console",
          "Intended Audience :: Developers",
          "Operating System :: POSIX :: Linux",
          "Programming Language :: Python :: 3.10",
          "Programming Language :: Python :: 3.11",
          "Programming Language :: Python :: 3.12",
          "Programming Language :: Python :: 3.13",
          "Programming Language :: Python :: 3.14",
          "Programming Language :: Python :: Implementation :: CPython",
          "Topic :: Software Development :: Libraries :: Python Modules",
      ],
      python_requires='>=3.10,<4.0',
      install_requires=[
          'rocksdict>=0.3.29,<1.0.0',
          'msgpack>=1.2.1,<2.0.0',
          'google-crc32c>=1.7.1,<2.0.0',
      ])
