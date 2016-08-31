"""Give user some play money to get started with for the demo."""
from decimal import Decimal
from pyramid.events import subscriber
from sqlalchemy.orm import Session

from websauna.utils.time import now
from websauna.wallet.ethereum.asset import get_toy_box, get_house_holdings, get_ether_asset
from websauna.wallet.ethereum.utils import bin_to_eth_address, bin_to_txid
from .events import InitialAddressCreation, WalletCreated


def give_toybox(event):
    from websauna.wallet.tests.eth.utils import send_balance_to_address, do_faux_deposit

    user = event.user

    toybox = get_toy_box(event.network)
    if not toybox:
        return

    amount = event.network.other_data["initial_assets"].get("toybox_amount")
    if not amount:
        return

    if not event.web3:
        # MockEthreumService test shortcut
        dbsession = Session.object_session(event.address)
        network = event.address.network
        house_holdings = get_house_holdings(toybox)
        op = do_faux_deposit(event.address, house_holdings.account.asset.id, Decimal(amount))
    else:
        # Generate initial operation to supply the user
        house_holdings = get_house_holdings(toybox)
        op = house_holdings.withdraw(Decimal(amount), event.address.address, "Starter assets for user {}".format(user.friendly_name))

        # Generate op.id
        dbsession = Session.object_session(user)
        dbsession.flush()

    assert op.id

    # Record this operation in user data so we can verify it later
    op_txs = user.user_data.get("starter_asset_txs", [])
    op_txs.append({"toybox": str(op.id)})
    user.user_data["starter_asset_txs"] = op_txs


def give_eth(event):
    """Feed user some test ETH from coinbase."""
    user = event.user

    # TODO: Rework this
    from websauna.wallet.tests.eth.utils import send_balance_to_address, do_faux_deposit

    amount = event.network.other_data["initial_assets"].get("eth_amount")
    if not amount:
        return

    # Supply eth from coinbase
    address = bin_to_eth_address(event.address.address)
    if event.web3:
        txid = send_balance_to_address(event.web3, address, Decimal(amount))
    else:
        # MockEthreumService test
        dbsession = Session.object_session(event.address)
        network = event.address.network
        asset = get_ether_asset(dbsession, network)
        op = do_faux_deposit(event.address, asset.id, Decimal(amount))
        txid = bin_to_txid(op.txid)

    # Record this operation in user data so we can verify it later
    op_txs = user.user_data.get("starter_asset_txs", [])
    op_txs.append({"eth": txid})
    user.user_data["starter_asset_txs"] = op_txs


@subscriber(InitialAddressCreation)
def give_starter_assets(event: InitialAddressCreation):
    """Put some initial assets on the user account."""

    asset_config = event.network.other_data.get("initial_assets")
    if not asset_config:
        return

    give_toybox(event)
    give_eth(event)


def check_wallet_creation(request) -> bool:
    """Check if we have notified this user about wallet creation yet.

    :return: True if this was a wallet creation event
    """
    user = request.user

    if not "wallet_creation_notified_at" in request.user.user_data:
        request.user.user_data["wallet_creation_notified_at"] = now().isoformat()
        request.registry.notify(WalletCreated(request, user))
        return True
    else:
        return False

