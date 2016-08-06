#!/bin/bash
#
# Rebuild demo db
#

set -e
set -u

dropdb wallet_demo
createdb wallet_demo
ws-sync-db websauna/wallet/conf/development.ini
ws-create-user websauna/wallet/conf/development.ini admin@example.com x
