#!/usr/bin/python3

# As its only command-line argument, this script accepts a URL to a
# /zuul-info/inventory.yaml file from a completed build (for a ref object, not
# a change/PR), or to the log tree where the zuul-info directory can be found.
# It should return the `zuul enqueue-ref` command necessary to rerun that and
# any other jobs for the same ref and pipeline.

import sys

import requests
import yaml

data = requests.get(sys.argv[1] + '/zuul-info/inventory.yaml').text
zuul_vars = yaml.safe_load(data)['all']['vars']['zuul']

print(
    'sudo zuul enqueue-ref '
    '--tenant=%s --trigger=%s --pipeline=%s --project=%s --ref=%s --newrev=%s'
    % (
        zuul_vars['tenant'],
        'gerrit',
        zuul_vars['pipeline'],
        zuul_vars['project']['name'],
        zuul_vars['ref'],
        zuul_vars['newrev']))
