#!/bin/sh

echo $*
case "$1" in
    push)
      exit 9
      ;;
    clone)
        dest=$3
        mkdir -p $dest/.git
        ;;
    version)
        echo "git version 1.0.0"
        exit 0
        ;;
esac
sleep 30
