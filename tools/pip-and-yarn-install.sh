#!/bin/bash
set -e

# Install both python and javascript requirements for tox.

# This script checks if yarn is installed in the current path.
# If not, if will install node using nodeenv, then install yarn from source
# using the npm from nodeenv.

# The script will run yarn to install javascript dependencies and will run
# the javascript build once at install time. It touches a stamp file so that
# the normal invocation only happens once.

if [[ -z $VIRUTAL_ENV ]]; then
    echo "$0 is only intended to be used from within a virtualenv"
    exit 1
fi

SRC_DIR=${SRC_DIR:-$(basedir $0/..)}
NODE_DIR=${NODE_DIR:-$SRC_DIR/node_modules}
NODE_STAMP=$NODE_DIR/.tox-stamp
YARN=${YARN:-$(command -v yarn)}
NPM_TARGET=${NPM_TARGET:-build}

# If nodeenv isn't in, this is a clean virtualenv, which means it's either
# a fresh install or a tox -r invocation.
# Force a reinstall of javascript depends.
if [[ ! -f $VIRTUAL_ENV/bin/nodeenv ]]; then
    rm -f $NODE_STAMP
fi

pip install $*

if [[ -z $YARN ]]; then
    YARN=$NODE_DIR/.bin/yarn
    # We're doing yarn in the virtualenv using nodeenv
    if [[ ! -f $YARN ]]; then
        echo "yarn not found, installing using nodeenv."
        echo
        echo "This is inefficient. Please see tools/install-js-tools.sh to"
        echo "install yarn and nodejs from distro packages."
        nodeenv -p "$VIRTUAL_ENV"
        hash -t npm
        # --no-save prevents it from being added to package.json
        npm install --no-save yarn
    fi
fi

# Don't re-install if we've already installed things.
if [[ ! -f $NODE_DIR/.tox-stamp ]]; then 
    $YARN install
    touch $NODE_DIR/.tox-stamp
fi

# Don't rebuild if the content is there.
if [[ ! -d $SRC_DIR/zuul/web/static ]]; then
    npm run $NPM_TARGET
fi
