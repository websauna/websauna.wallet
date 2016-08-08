#!/bin/bash
#
# Rebuild demo db with network definitions, house wallets and toy box assets
#

set -u

# Don't run service while we nuke the db
pkill ethereum-service
sleep 5
dropdb wallet_demo
createdb wallet_demo
ws-sync-db websauna/wallet/conf/development.ini
# Service is needed in order to bootstrap operatons to complete
ethereum-service websauna/wallet/conf/development.ini &
sleep 5
wallet-bootstrap websauna/wallet/conf/development.ini
ws-create-user websauna/wallet/conf/development.ini admin@example.com x
# We are done with the service
pkill -f ethereum-service
