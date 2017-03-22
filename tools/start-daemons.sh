#!/bin/bash
# For docker testing, start daemons
nohup /usr/bin/mysqld_safe &
bash -x /etc/init.d/zookeeper start
