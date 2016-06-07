import sqlalchemy
from collections import OrderedDict

from decimal import Decimal
from pyramid_layout.panel import panel_config
from websauna.wallet.models import Account, UserOwnedAccount, Asset
from websauna.wallet.utils import format_asset_amount

from . import admins


@panel_config(name='admin_panel', context=admins.UserAccountAdmin, renderer='admin/user_owned_account_panel.html')
def user_owned_account(context, request, controls=True):
    """Admin panel for Users."""

    dbsession = request.dbsession

    # Query all liabilities

    # NOTE: This is a bad SQLAlchemy example as this performances one query
    # per one asset. One could perform this with a single group by query

    liabilities = OrderedDict()
    account_summer = sqlalchemy.func.sum(Account.denormalized_balance).label("denormalized_balance")

    for asset in dbsession.query(Asset).order_by(Asset.name.asc()):
        total_balances = dbsession.query(account_summer).filter(Account.asset == asset).join(UserOwnedAccount).all()
        balance = total_balances[0][0] or Decimal(0)
        liabilities[asset.name] = format_asset_amount(balance, asset.asset_format)

    # These need to be passed to base panel template,
    # so it knows how to render buttons
    model_admin = context

    return locals()
