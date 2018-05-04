#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys

from setuptools import find_packages
import uuid
import imp


try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup


if sys.argv[-1] == 'publish':
    os.system('python setup.py sdist upload')
    sys.exit()

with open(os.path.join(os.path.dirname(__file__), 'README.rst')) as f:
    readme = f.read()

# Avoiding import so we don't execute __init__.py, which has imports
# that aren't installed until after installation.
_meta = imp.load_source('_meta', 'tableintuit/__meta__.py')

packages = find_packages()


classifiers = [
    'Development Status :: 4 - Beta',
    'Intended Audience :: Developers',
    'License :: OSI Approved :: MIT License',
    'Operating System :: OS Independent',
    'Programming Language :: Python',
    'Programming Language :: Python :: 3.4',
    'Topic :: Software Development :: Libraries :: Python Modules',
]

setup(
    name='tableintuit',
    version=_meta.__version__,
    description='Guess the structure and datatypes of row data, such as from a spreadsheet',
    long_description=readme,
    packages=packages,
    install_requires=[
        'tabulate'
    ],

    author=_meta.__author__,
    author_email='eric@civicknowledge.com',
    url='https://github.com/Metatab/tableintuit.git',
    license='MIT',
    classifiers=classifiers,
    entry_points={
        'console_scripts': [
            'tintuit=tableintuit.cli:main',
        ],
    },
)
