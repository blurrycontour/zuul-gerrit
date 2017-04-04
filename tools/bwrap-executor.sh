#!/bin/bash
# The intention here is to isolate anything the executor must run as much as
# we can within reason.
# Explanation from less obvious things follows:
#
# * Ansible and SSH both require access to /dev/null so we need --dev /dev
# * Ansible wants to read /proc, so we need --proc /proc
# * 65534 is the nobody/nogroup UID/GID
# * work_dir is bind mounted and intentionally writable. It should contain
#   any and all data that playbooks need, and will be used for temporary
#   storage of artifacts between playbook phases.
#

work_dir=$1
shift
state_dir=$1
shift

# We still run as ourselves
GID=$(id -g)

set -euo pipefail

(exec bwrap --dir /tmp \
      --tmpfs /tmp \
      --dir /var \
      --dir /var/tmp \
      --dir /run/user/${UID} \
      --ro-bind /usr /usr \
      --ro-bind /lib /lib \
      --ro-bind /lib64 /lib64 \
      --ro-bind /bin /bin \
      --ro-bind /sbin /sbin \
      --ro-bind /etc/resolv.conf /etc/resolv.conf \
      --ro-bind ${state_dir} ${state_dir} \
      --dir ${work_dir} \
      --bind ${work_dir} ${work_dir} \
      --dev /dev \
      --dir ${HOME} \
      --chdir / \
      --unshare-all \
      --share-net \
      --uid ${UID} \
      --gid ${GID} \
      --file 11 /etc/passwd \
      --file 12 /etc/group \
      "$@") \
      11< <(getent passwd ${UID} 65534) \
      12< <(getent group ${GID} 65534)
