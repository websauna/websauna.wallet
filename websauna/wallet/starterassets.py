"""Give user some play money to get started with for the demo."""
from decimal import Decimal
from pyramid.events import subscriber
from sqlalchemy.orm import Session

from websauna.system import user
from websauna.wallet.ethereum.asset import get_toy_box, get_house_holdings
from websauna.wallet.ethereum.utils import bin_to_eth_address
from websauna.wallet.tests.eth.utils import send_balance_to_address
from .events import InitialAddressCreation
from .models import UserCryptoOperation
from .models import UserCryptoAddress
from .models import CryptoAddressCreation
from .models import AssetNetwork


def give_toybox(event):
    user = event.user

    toybox = get_toy_box(event.network)
    if not toybox:
        return

    amount = event.network["initial_assets"].get("toybox_amount")
    if not amount:
        return

    # Generate initial operation to supply the user
    house_holdings = get_house_holdings(toybox)
    op = house_holdings.withdraw(Decimal(amount), event.address.address, "Starter assets for user {}".format(user.friendly_name))

    # Generate op.id
    dbsession = Session.object_session(user)
    dbsession.flush()

    assert op.id

    # Record this operation in user data so we can verify it later
    op_txs = user.user_data.get("starter_asset_ops", [])
    op_txs.append(str(op.id))
    user.user_data["starter_asset_ops"] = op_txs


def give_eth(event):
    user = event.user

    amount = event.network.other_data["initial_assets"].get("eth_amount")
    if not amount:
        return

    # Supply eth from coinbase
    address = bin_to_eth_address(event.address.address)
    txid = send_balance_to_address(event.web3, address, Decimal(amount))

    # Record this operation in user data so we can verify it later
    op_txs = user.user_data.get("starter_asset_txs", [])
    op_txs.append(txid)
    user.user_data["starter_asset_txs"] = op_txs


@subscriber(InitialAddressCreation)
def give_starter_assets(event: InitialAddressCreation):
    """Put some initial assets on the user account."""

    asset_config = event.network.other_data.get("initial_assets")
    if not asset_config:
        return

    give_toybox(event)
    give_eth(event)





