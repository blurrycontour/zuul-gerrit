# -*- coding: utf-8 -*-
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys, os, datetime
import subprocess
import re
from zuul import version

# The minimum version to link to
min_version = (3, 3, 0)

sys.path.insert(0, os.path.abspath('../..'))
# -- General configuration ----------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom ones.
extensions = [
    'sphinx.ext.autodoc',
    'sphinx_autodoc_typehints',
    'sphinx.ext.graphviz',
    'sphinxcontrib.programoutput',
    'sphinxcontrib.openapi',
    'zuul_sphinx',
    'zuul.sphinx.ansible',
    'reno.sphinxext',
    'sphinx_rtd_theme',
]

# autodoc generation is a bit aggressive and a nuisance when doing heavy
# text edit cycles.
# execute "export SPHINX_DEBUG=1" in your terminal to disable

primary_domain = 'zuul'

# The suffix of source filenames.
source_suffix = '.rst'

# The master toctree document.
master_doc = 'index'

# General information about the project.
project = u'Zuul'
copyright = u'2012-%s, Zuul project contributors' % datetime.date.today().year

doc_root = os.environ.get('ZUUL_DOC_ROOT', '/docs/%s' % (project.lower()))

# If true, '()' will be appended to :func: etc. cross-reference text.
add_function_parentheses = True

# If true, the current module name will be prepended to all description
# unit titles (such as .. function::).
add_module_names = True

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = 'sphinx'

# -- Options for HTML output --------------------------------------------------

# The theme to use for HTML and HTML Help pages.  Major themes that come with
# Sphinx are currently 'default' and 'sphinxdoc'.
html_theme = "sphinx_rtd_theme"
# This adds a <link rel=canonical> tag
html_baseurl = f'https://zuul-ci.org{doc_root}/latest'

if version.is_release:
    current_version = version.release_string
    version = version.release_string
    versions = [('latest', f'{doc_root}/latest/')]
else:
    # Uncomment this if we want to use the in-development version
    # number (eg 4.10.5.dev4 887cf31e4 )
    # version = version.get_version_string()
    version = 'latest'
    current_version = 'latest'
    versions = [('latest', f'{doc_root}/latest/')]

try:
    output = subprocess.check_output(['git', 'tag']).decode('utf8')
except subprocess.CalledProcessError:
    output = ''

interesting_tags = []
for tag in output.splitlines():
    if re.match(r'^\d+\.\d+\.\d+$', tag):
        parts = tuple(map(int, tag.split('.')))
        if parts < min_version:
            continue
        interesting_tags.append((parts, tag))
for parts, tag in reversed(sorted(interesting_tags, key=lambda x: x[0])):
    versions.append((tag, f'{doc_root}/{tag}/'))

# Theme options are theme-specific and customize the look and feel of a theme
# further.  For a list of options available for each theme, see the
# documentation.
html_theme_options = {
    'collapse_navigation': False,
    'navigation_depth': -1,
    'logo_only': True,
    'style_nav_header_background': '#41B6E6',
}

html_context = {
    # This controls what is displayed at the top of the navbar.
    'version': version,
    # This controls what the caret selection displays at the bottom of
    # the navbar.
    'current_version': current_version,
    # A tuple of (slug, url)
    'versions': versions,
}

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']

# These paths are either relative to html_static_path
# or fully qualified paths (eg. https://...)
html_css_files = [
    'custom.css',
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# The name of an image file (relative to this directory) to place at the top
# of the sidebar.
html_logo = '_static/logo.svg'

# Output file base name for HTML help builder.
htmlhelp_basename = '%sdoc' % project

# Grouping the document tree into LaTeX files. List of tuples
# (source start file, target name, title, author, documentclass
# [howto/manual]).
latex_documents = [
    ('index',
     '%s.tex' % project,
     u'%s Documentation' % project,
     u'Zuul contributors', 'manual'),
]

# Example configuration for intersphinx: refer to the Python standard library.
#intersphinx_mapping = {'http://docs.python.org/': None}

# The name of an image file (within the static path) to use as favicon of the
# docs.  This file should be a Windows icon file (.ico) being 16x16 or 32x32
# pixels large.
#html_favicon = None

# Additional Zuul role paths
zuul_role_paths = []
