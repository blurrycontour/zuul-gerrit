# -*- coding: utf-8 -*-
#

# Add any Sphinx extension module names here, as strings. They can be extensions
# coming with Sphinx (named 'sphinx.ext.*') or your custom ones.
extensions = ['sphinx.ext.autodoc', 'sphinx.ext.intersphinx']

intersphinx_mapping = {'python': ('http://docs.python.org/2.7', None)}

# The master toctree document.
master_doc = 'index'

# General information about the project.
copyright = u'2012, OpenStack'

# One entry per manual page. List of tuples
# (source start file, name, description, authors, manual section).
man_pages = [
    ('index', 'zuul', u'Zuul Documentation',
     [u'OpenStack'], 1)
]
