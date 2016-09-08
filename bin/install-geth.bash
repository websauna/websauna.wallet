#!/bin/bash
#
# Install geth monolithic binary
#

if [ ! -e geth/geth ] ; then
    wget -O geth.tar.bz2 https://github.com/ethereum/go-ethereum/releases/download/v1.4.11/geth-Linux64-20160819135300-1.4.11-fed692f.tar.bz2
    install -d geth
    cd geth
    tar -xjf ../geth.tar.bz2
    echo "Geth installed at $PWD/geth"
else
    echo "Geth already installed at $PWD/geth/geth"
fi
