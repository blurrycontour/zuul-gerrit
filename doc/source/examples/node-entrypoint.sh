#!/bin/bash

if [ -n "${START_K1S}" ] ; then
    k1s &
fi

/usr/sbin/sshd -D
