#!/bin/sh -e

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

SUBJECT=${SUBJECT:-'/C=US/ST=California/L=Oakland/O=Company Name/OU=Org'}
TOOLSDIR=$(cd "$(dirname "$0")"; pwd -P)
CONFIG="$TOOLSDIR/openssl.cnf"

make_ca() {
    mkdir "${CAROOT}/demoCA"
    mkdir "${CAROOT}/demoCA/reqs"
    mkdir "${CAROOT}/demoCA/newcerts"
    mkdir "${CAROOT}/demoCA/crl"
    mkdir "${CAROOT}/demoCA/private"
    chmod 700 "${CAROOT}/demoCA/private"
    touch "${CAROOT}/demoCA/index.txt"
    touch "${CAROOT}/demoCA/index.txt.attr"
    mkdir "${CAROOT}/certs"
    mkdir "${CAROOT}/keys"
    mkdir "${CAROOT}/keystores"
    chmod 700 "${CAROOT}/keys"
    chmod 700 "${CAROOT}/keystores"

    openssl req \
            -config "${CONFIG}" \
            -new \
            -nodes \
            -subj "$SUBJECT/CN=caroot" \
            -keyout "${CAROOT}/demoCA/private/cakey.pem" \
            -out "${CAROOT}/demoCA/reqs/careq.pem"
    openssl ca \
            -config "${CONFIG}" \
            -create_serial \
            -days 3560 \
            -batch \
            -selfsign \
            -extensions v3_ca \
            -out "${CAROOT}/demoCA/cacert.pem" \
            -keyfile "${CAROOT}/demoCA/private/cakey.pem" \
            -infiles "${CAROOT}/demoCA/reqs/careq.pem"
    cp "${CAROOT}/demoCA/cacert.pem" "${CAROOT}/certs"
}

make_client() {
    openssl req \
            -config "${CONFIG}" \
            -new \
            -nodes \
            -subj "$SUBJECT/CN=client" \
            -keyout "${CAROOT}/keys/clientkey.pem" \
            -out "${CAROOT}/demoCA/reqs/clientreq.pem"
    openssl ca \
            -config "${CONFIG}" \
            -batch \
            -policy policy_anything \
            -days 3560 \
            -out "${CAROOT}/certs/client.pem" \
            -infiles "${CAROOT}/demoCA/reqs/clientreq.pem"
}

make_server() {
    SERVER="${1}"
    openssl req \
            -config "${CONFIG}" \
            -new \
            -nodes \
            -subj "$SUBJECT/CN=${SERVER}" \
            -keyout "${CAROOT}/keys/${SERVER}key.pem" \
            -out "${CAROOT}/demoCA/reqs/${SERVER}req.pem"
    openssl ca \
            -config "${CONFIG}" \
            -batch \
            -policy policy_anything \
            -days 3560 \
            -out "${CAROOT}/certs/${SERVER}.pem" \
            -infiles "${CAROOT}/demoCA/reqs/${SERVER}req.pem"
    cat "${CAROOT}/certs/${SERVER}.pem" "${CAROOT}/keys/${SERVER}key.pem" \
        > "${CAROOT}/keystores/${SERVER}.pem"
}

make_keystore() {
    SERVER="${1}"
    openssl pkcs12 \
            -export \
            -in "${CAROOT}/keystores/${SERVER}.pem" \
            -out "${CAROOT}/keystores/${SERVER}.pkcs12" \
            -password pass:keystorepassword

    keytool -v \
            -import \
            -trustcacerts \
            -noprompt \
            -alias cacert \
            -file "${CAROOT}/certs/cacert.pem" \
            -keystore "${CAROOT}/keystores/${SERVER}.jks" \
            -storepass keystorepassword

    keytool -v \
            -importkeystore \
            -srckeystore "${CAROOT}/keystores/${SERVER}.pkcs12"  \
            -srcstoretype PKCS12 \
            -srcalias 1 \
            -srcstorepass keystorepassword \
            -destkeystore "${CAROOT}/keystores/${SERVER}.jks" \
            -deststoretype JKS \
            -destalias "${SERVER}" \
            -deststorepass keystorepassword
}

help() {
    echo "$(basename ${0}) CAROOT [SERVER...]"
    echo
    echo "  CAROOT is the path to a directory in which to store the CA"
    echo "         and certificates."
    echo "  SERVER one or more FQDN of a server(s) for which a certificate"
    echo "         should be generated"
    echo
    echo "  Environment:"
    echo "    SUBJECT .. certificate subject"
    echo "               default: /C=US/ST=California/L=Oakland/O=Company Name/OU=Org"
}

if [ ! -f ~/.rnd ]; then
    echo "No ~/.rnd!"
    echo "Generate one (e.g.: dd if=/dev/urandom of=~/.rnd bs=256 count=1)"
    echo
    help
    exit 1
fi

if [ ! -d "${CAROOT}" ]; then
    echo "CAROOT must be a directory"
    help
    exit 1
fi

cd "${CAROOT}"
CAROOT="$(pwd)"

if [ ! -d "${CAROOT}/demoCA" ]; then
    echo 'Generate CA'
    make_ca
    echo 'Generate client certificate'
    make_client
fi

for server in ${@:2}; do
  if [ -f "${CAROOT}/certs/${server}.pem" ]; then
      echo "Certificate for ${server} already exists"
  fi
  if [ "${server}" != "" ]; then
      make_server "${server}"
      echo "Generate keystore"
      make_keystore "${server}"
  fi
done
