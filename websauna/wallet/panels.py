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
    model_admin = context
    return locals()
