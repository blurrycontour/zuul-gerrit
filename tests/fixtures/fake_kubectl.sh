#!/bin/bash

# Script arguments look like:
# --kubeconfig=/tmp/tmppm0yyqvv/zuul-test/builds/c21fc1eb7e2c469cb4997d688252dc3c/work/.kube/config --context=zuul-ci-abcdefg:zuul-worker/ -n zuul-ci-abcdefg port-forward pod/fedora-abcdefg 37303:19885

# Get the last argument to the script
arg=${@:$#}

# Split on the colon
ports=(${arg//:/ })

echo "Forwarding from 127.0.0.1:${ports[0]} -> ${ports[1]}"

while true; do
    sleep 5
done
