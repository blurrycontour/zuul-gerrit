#!/bin/bash

if [ ! -e $1/bin/grunt ] ; then
  nodeenv -p $2 --node=0.10.24 || true
  npm install -g bower@1.2.8 grunt@0.4.2 grunt-cli@0.1.11
  npm install
  bower install
fi
