#!/bin/bash

# Zuul needs to be able to connect to the remote systems in order to
# start.

wait_for_mysql() {
    echo `date -Iseconds` "Wait for mysql to start"
    for i in $(seq 1 120); do
        cat < /dev/null > /dev/tcp/mysql/3306 && return
        sleep 1
    done

    echo `date -Iseconds` "Timeout waiting for mysql"
    exit 1
}

wait_for_gitlab() {
    echo `date -Iseconds` "Wait for zuul user to be created"
    for i in $(seq 1 300); do
        [ $(curl -s -o /dev/null -w "%{http_code}" http://gitlab:8081/api/v4/users/zuul/status) = "200" ] && return
        sleep 1
    done

    echo `date -Iseconds` "Timeout waiting for gitlab"
    exit 1
}

wait_for_mysql
wait_for_gitlab
