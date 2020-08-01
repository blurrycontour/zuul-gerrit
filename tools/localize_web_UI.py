#!/usr/bin/env python

# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.


import argparse
import json
import os
import re


DESCRIPTION = """
This script can be used to generate a JSON-like list of the strings that are
translated in the Web UI.
"""


def main():
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument('--path', help="Path to the web src root directory.")
    parser.add_argument('--lang', default='en_US',
                        help='Use this language\'s translations file to '
                             'pre-fill translations in the output.')
    args = parser.parse_args()

    lookup = r'[\W {]+[_t]\(((?P<quote>\'?).+(?P=quote))(?:,\s*\{.+\})?\)\}'

    xx = re.compile(lookup)

    translatableStrings = {}

    translationPath = 'locales/%s/translations.json' % args.lang
    with open(os.path.join(args.path,
                           translationPath), 'r') as src:
        jsonSrc = json.load(src)

    for dirpath, dirnames, files in os.walk(args.path):
        for fname in files:
            if any(fname.lower().endswith(ext) for ext in ('.js', '.jsx')):
                with open(os.path.join(dirpath, fname), 'r') as jsFile:
                    for trans in xx.findall(jsFile.read()):
                        string = trans[0]
                        if trans[1] == "'":
                            string = string[1:-1]
                        stringData = {
                            'paths': [os.path.join(dirpath, fname), ],
                            'isVar': trans[1] != "'"}
                        if string in translatableStrings:
                            if (stringData['paths'][0] not in
                                translatableStrings[string]['paths']):
                                translatableStrings[string]['paths'] +=\
                                    stringData['paths']
                        else:
                            translatableStrings[string] = stringData

    fakeJSON = """
# /!\\ This is NOT a valid JSON object!
# Remove all comments after editing.

{\n"""
    variablesList = """# The following are translated variables.
# The actual values to translate need to be found in the source code.\n"""
    for s in sorted(translatableStrings.keys()):
        for path in sorted(translatableStrings[s]['paths']):
            if translatableStrings[s]['isVar']:
                variablesList += '# In %s\n' % path
            else:
                fakeJSON += '# In %s\n' % path
        # TODO handle dot notation
        if translatableStrings[s]['isVar']:
            variablesList += s + '\n'
        else:
            fakeJSON += '  "%s": "%s",\n' % (repr(s)[1:-1],
                                             repr(jsonSrc.get(s, ''))[1:-1])
    # Add unlisted entries from the original translations.JSON file
    fakeJSON += ("# These entries were not found in the source code.\n"
                 "# They are either obsolete or refer to variable values "
                 "that need to be found in the code.\n")
    diffEntries = set(jsonSrc.keys()).difference(
        set(translatableStrings.keys()))
    for s in sorted(diffEntries):
        if isinstance(jsonSrc[s], dict):
            # please don't use too much depth!
            prettyData = '{\n'
            for k in sorted(jsonSrc[s].keys()):
                prettyData += '    "%s": "%s",\n' % (repr(k)[1:-1],
                                                     repr(jsonSrc[s][k])[1:-1])
            prettyData = prettyData[:-2] + '\n  }'
        else:
            prettyData = '"%s"' % repr(jsonSrc[s])[1:-1]
        fakeJSON += '  "%s": %s,\n' % (repr(s)[1:-1], prettyData)
    fakeJSON += fakeJSON[:-2] + '\n}'
    print(fakeJSON)
    # TODO the regex is wonky used to catch vars is wonky
    # print(variablesList)


if __name__ == '__main__':
    main()
