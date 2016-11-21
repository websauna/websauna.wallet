import transaction
from websauna.system.http import Request
from websauna.system.user.models import User
from websauna.wallet.models import UserCryptoAddress


def nuke_wallets(request: Request):
    """Reset testnet wallets."""
    dbsession = request.dbsession

    with transaction.manager:
        for user in dbsession.query(User).all():

            # Reset creation flag
            if "wallet_creation_notified_at" in user.user_data:
                del user.user_data["wallet_creation_notified_at"]

        # Boom
        dbsession.query(UserCryptoAddress).delete()

