#!/bin/sh

# Zuul needs to be able to connect to the remote systems in order to
# start.

for i in $(seq 1 120); do
    [ $(curl -s -o /dev/null -w "%{http_code}" http://admin:secret@gerrit:8080/a/accounts/zuul/sshkeys) = "200" ] && exit 0
    sleep 1
done

echo "Timeout waiting for gerrit"
exit 1
