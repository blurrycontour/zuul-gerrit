Steps used to create our certs

# Generate CA cert
$ openssl req -out ca.pem -new -x509 -subj "/C=US/ST=Texas/L=Austin/O=OpenStack Foundation/CN=gearman-ca"

Generating a 2048 bit RSA private key
.+++
...........................................+++
writing new private key to 'privkey.pem'
Enter PEM pass phrase:
Verifying - Enter PEM pass phrase:
-----

# Generate server keys
$ openssl genrsa -out server.key 1024

Generating RSA private key, 1024 bit long modulus
........++++++
.............................................................................................................................++++++
e is 65537 (0x10001)

$ openssl req -key server.key -new -out server.req -subj "/C=US/ST=Texas/L=Austin/O=OpenStack Foundation/CN=gearman-server"
$ echo "00" > file.srl
$ openssl x509 -req -in server.req -CA ca.pem -CAkey privkey.pem -CAserial file.srl -out server.pem

Signature ok
subject=/C=US/ST=Texas/L=Austin/O=OpenStack Foundation/CN=gearman-server
Getting CA Private Key
Enter pass phrase for privkey.pem:

# Generate client keys
$ openssl genrsa -out client.key 1024

Generating RSA private key, 1024 bit long modulus
....................++++++
.................................++++++
e is 65537 (0x10001)

$ openssl req -key client.key -new -out client.req -subj "/C=US/ST=Texas/L=Austin/O=OpenStack Foundation/CN=gearman-client"
$ echo "00" > file.srl
$ openssl x509 -req -in client.req -CA ca.pem -CAkey privkey.pem -CAserial file.srl -out client.pem

Signature ok
subject=/C=US/ST=Texas/L=Austin/O=OpenStack Foundation/CN=gearman-client
Getting CA Private Key
Enter pass phrase for privkey.pem:

# Test with geard
# You'll need 2 terminal windows
geard --ssl-ca ca.pem --ssl-cert server.pem --ssl-key server.key -d
openssl s_client -connect localhost:4730 -key client.key -cert client.pem -CAfile ca.pem
