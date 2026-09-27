"""
*******
Configs
*******

**Configs** is an INI configuration parsing package, written for humans.

Usage
=====
Load a config file::

    >>> import configs
    >>> c = configs.load('sample.conf')
    >>> c['general']
    {'foo': 'baz'}

See the full documentation at `configs.rtfd.org <http://configs.rtfd.org>`_.

The repo is at `bitbucket.org/moigagoo/configs <https://bitbucket.org/moigagoo/configs>`_.
"""

__title__ = 'configs'
__version__ = '3.0.3'
__author__ = 'Konstantin Molchanov'
__license__ = 'MIT'

from .section import Section
from .config import Config
from .api import load
