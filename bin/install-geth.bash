#!/bin/bash
#
# Install geth monolithic binary
#

set -e
set -u

if [ ! -e geth/geth ] ; then
    wget -O geth.tar.gz https://gethstore.blob.core.windows.net/builds/geth-linux-amd64-1.5.9-a07539fb.tar.gz
    install -d geth
    cd geth
    tar -xzf ../geth.tar.gz
    echo "Geth installed at $PWD/geth"
else
    echo "Geth already installed at $PWD/geth/geth"
fi
