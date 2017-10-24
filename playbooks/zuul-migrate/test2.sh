#!/bin/bash

set -ex

source /home/zuul/functions

setup_temp_space release-tag

echo $*

exit 0
