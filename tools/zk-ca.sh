#!/bin/sh

# Copyright 2020 Red Hat, Inc
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

# Manage a CA for Zookeeper

CAROOT=$1
SERVER=$2
KEYSTORE_PASSWORD=foobar
EXPORT_PASSWORD=foobar

make_ca() {
    mkdir $CAROOT/demoCA
    mkdir $CAROOT/demoCA/reqs
    mkdir $CAROOT/demoCA/newcerts
    mkdir $CAROOT/demoCA/crl
    mkdir $CAROOT/demoCA/private
    chmod 700 $CAROOT/demoCA/private
    touch $CAROOT/demoCA/index.txt
    touch $CAROOT/demoCA/index.txt.attr
    mkdir $CAROOT/certs
    mkdir $CAROOT/keys
    mkdir $CAROOT/keystores
    chmod 700 $CAROOT/keys
    chmod 700 $CAROOT/keystores

    openssl req -new -nodes -subj '/C=US/ST=California/L=Oakland/O=Company Name/OU=Org/CN=caroot' -keyout $CAROOT/demoCA/private/cakey.pem -out $CAROOT/demoCA/reqs/careq.pem
    openssl ca -create_serial -out $CAROOT/demoCA/cacert.pem -days 1095 -batch -keyfile $CAROOT/demoCA/private/cakey.pem -selfsign -extensions v3_ca -infiles $CAROOT/demoCA/reqs/careq.pem
    keytool -import -noprompt -keystore $CAROOT/keystores/truststore.jks -file $CAROOT/demoCA/cacert.pem -alias caroot -deststorepass "$KEYSTORE_PASSWORD"
}

make_client() {
    openssl req -new -nodes -subj '/C=US/ST=California/L=Oakland/O=Company Name/OU=Org/CN=client' -keyout $CAROOT/keys/clientkey.pem -out $CAROOT/demoCA/reqs/clientreq.pem
    openssl ca -batch -policy policy_anything -out $CAROOT/certs/client.pem -infiles $CAROOT/demoCA/reqs/clientreq.pem
}

make_server() {
    openssl req -new -nodes -subj "/C=US/ST=California/L=Oakland/O=Company Name/OU=Org/CN=$SERVER" -keyout $CAROOT/keys/${SERVER}key.pem -out $CAROOT/demoCA/reqs/${SERVER}req.pem
    openssl ca -batch -policy policy_anything -out $CAROOT/certs/$SERVER.pem -infiles $CAROOT/demoCA/reqs/${SERVER}req.pem
    openssl pkcs12 -export -in $CAROOT/certs/$SERVER.pem -inkey $CAROOT/keys/${SERVER}key.pem -name $SERVER -passout "pass:$EXPORT_PASSWORD" > $CAROOT/keystores/$SERVER.p12
    keytool -importkeystore -destkeystore $CAROOT/keystores/$SERVER.pem -srckeystore $CAROOT/keystores/$SERVER.p12 -srcstoretype pkcs12 -alias $SERVER -deststorepass "$KEYSTORE_PASSWORD" -srcstorepass "$EXPORT_PASSWORD"
    rm -f $CAROOT/keystores/$SERVER.p12
}

if [ ! -d "$CAROOT" ]; then
    echo "$CAROOT must be a directory"
    exit 1
fi

if [ ! -d "$CAROOT/demoCA" ]; then
    echo 'Generate CA'
    make_ca
    echo 'Generate client certificate'
    make_client
fi

make_server
