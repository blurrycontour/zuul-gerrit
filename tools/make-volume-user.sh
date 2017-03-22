#!/bin/bash
set -eux
USER=$1
VOLUME_UID=$(stat --format="%u" $PWD)
USER_UID=$(id -u $USER || :)
if [ "$USER_UID" ] ; then
    if [ "$VOLUME_UID" != "$USER_UID" ] ; then
        echo "$USER already exists with UID == $USER_UID but volume has UID == $VOLUME_UID. Aborting"
        exit 1
    fi
else
    adduser --uid $VOLUME_UID --gecos '' --disabled-password --disabled-login $USER
fi
