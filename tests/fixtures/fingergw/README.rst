Steps used to create our certs

# Generate CA cert
$ openssl req -new -newkey rsa:2048 -nodes -keyout root-ca.key -x509 -days 3650 -out root-ca.pem -subj "/C=US/ST=Texas/L=Austin/O=OpenStack Foundation/CN=fingergw-ca"

# Generate server keys
$ CLIENT='server'
$ openssl req -new -newkey rsa:2048 -nodes -keyout $CLIENT.key -out $CLIENT.csr -subj "/C=US/ST=Texas/L=Austin/O=OpenStack Foundation/CN=nodepool-$CLIENT"
$ openssl x509 -req -days 3650 -in $CLIENT.csr -out $CLIENT.pem -CA root-ca.pem -CAkey root-ca.key -CAcreateserial


# Generate client keys
$ CLIENT='client'
$ openssl req -new -newkey rsa:2048 -nodes -keyout $CLIENT.key -out $CLIENT.csr -subj "/C=US/ST=Texas/L=Austin/O=OpenStack Foundation/CN=fingergw-$CLIENT"
$ openssl x509 -req -days 3650 -in $CLIENT.csr -out $CLIENT.pem -CA root-ca.pem -CAkey root-ca.key -CAcreateserial
