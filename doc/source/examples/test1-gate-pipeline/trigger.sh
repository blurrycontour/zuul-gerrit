#!/bin/bash

if [ -f c3 ]; then
    sleep 20
    exit 0
fi
if [ -f c2 ]; then
    exit 0
fi
if [ -f c1 ]; then
    sleep 60
    exit 0
fi
