from pyramid.events import subscriber
from sqlalchemy.orm import Session

from .events import CryptoOperationComplete, InitialAddressCreation, IncomingCryptoDeposit
from .models import UserCryptoOperation
from .models import UserCryptoAddress
from .models import CryptoAddressCreation
from .models import CryptoAddressDeposit
from .models import AssetNetwork
from .models import CryptoAddress



@subscriber(CryptoOperationComplete)
def initial_address_creation_checker(event: CryptoOperationComplete):
    """Check completed evennts and transfor one to initial address creation if needed."""
    op = event.op
    registry = event.registry

    user_op = UserCryptoOperation.get_from_op(op)

    if user_op:
        user = user_op.user
        if isinstance(op, CryptoAddressCreation):
            network = op.network
            assets = UserCryptoAddress.get_user_asset_accounts_by_network(user, network)
            if not assets:
                registry.notify(InitialAddressCreation(user, network, op, op.address, registry, event.web3))



@subscriber(IncomingCryptoDeposit)
def mark_deposit_for_user(event: IncomingCryptoDeposit):
    """If we have incoming transfer to an user address, make sure we have data to display this to the user."""

    op = event.op
    registry = event.registry
    dbsession = Session.object_session(op)

    # We have operation in process for this already
    user_op = UserCryptoOperation.get_from_op(op)
    if user_op:
        return

    # Check if we are depositing to user address
    address = op.crypto_account.address
    ua = dbsession.query(UserCryptoAddress).filter_by(address=address).one_or_none()

    # Yes thisop is to some specific user address
    if ua:
        uco = UserCryptoOperation(user=ua.user, crypto_operation=op)
        dbsession.add(uco)


