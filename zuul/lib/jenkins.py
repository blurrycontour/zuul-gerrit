# -*- coding: utf-8 -*-
# Copyright 2017 Red Hat
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

# Decrypt jenkins secrets
# Inspired from http://thiébaud.fr/jenkins_credentials.html

import base64
import os
import xml.dom.minidom

from hashlib import sha256
from Crypto.Cipher import AES


def decrypt(jenkins_dir):
    def read(path):
        return open(os.path.join(jenkins_dir, path), "rb").read()
    try:
        master_key = read("secrets/master.key")
        hudson_file = read("secrets/hudson.util.Secret")
        file_file = read("secrets/org.jenkinsci.plugins.plaincredentials."
                         "impl.FileCredentialsImpl")
        credencial = read("credentials.xml")
    except OSError:
        raise RuntimeError("Couldn't read jenkins files")

    text_key = AES.new(sha256(master_key).digest()[:16], AES.MODE_ECB).decrypt(
        hudson_file)[:16]
    file_key = AES.new(sha256(master_key).digest()[:16], AES.MODE_ECB).decrypt(
        file_file)[:16]

    creds = xml.dom.minidom.parseString(credencial).getElementsByTagName(
        "java.util.concurrent.CopyOnWriteArrayList")[0]
    secrets = {}

    for node in creds.childNodes:
        if node.nodeType == node.TEXT_NODE:
            continue

        def get(tag):
            try:
                child = node.getElementsByTagName(tag)[0].firstChild
                if child is None:
                    return ""
                return child.data
            except:
                print("Couldn't decode %s" % node.toxml())
                raise

        def decrypt(tag, key=text_key):
            data = AES.new(key, AES.MODE_ECB).decrypt(
                base64.b64decode(get(tag)))
            if b"::::MAGIC::::" in data:
                data = data[:data.index(b"::::MAGIC::::")]
            # Jenkins uses a weird padding for file, remove it from known type
            elif b"\x00\x00" in data[-32:]:
                # Tarball padding
                data = data[:data.rindex(b"\x00\x00") + 2]
            elif b"\x0a" in data[-32:]:
                # Textfile padding
                data = data[:data.rindex(b"\x0a") + 1]
            return data

        secret_id = get("id")
        secret = {
            "description": get("description"),
            "type": node.tagName.split(".")[-1],
        }
        if secret_id in secrets:
            raise RuntimeError("Secret id %s already defined" % secret_id)
        if secret["type"] == "StringCredentialsImpl":
            secret["secret"] = decrypt("secret").decode('utf-8')
        elif secret["type"] == "BasicSSHUserPrivateKey":
            # Skipping ssh private key
            pass
        elif secret["type"] == "FileCredentialsImpl":
            secret["fileName"] = get("fileName")
            secret["content"] = decrypt("data", key=file_key)
        elif secret["type"] == "UsernamePasswordCredentialsImpl":
            secret["username"] = get("username")
            secret["password"] = decrypt("password").decode('utf-8')
        else:
            raise RuntimeError("Unknown secret type %s" % node.toxml())
        secrets[secret_id] = secret
    return secrets


if __name__ == "__main__":
    print(decrypt("/var/lib/jenkins"))
