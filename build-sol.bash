#!/bin/bash
#
# Compile sol contracts
#

set -e
set -u

pushd `pwd`
cd websauna/wallet/ethereum
populus compile
popd