from decimal import Decimal

from websauna.wallet.models import AssetClass


formats = {
    AssetClass.fiat: "{:0,.2f}",
}

def get_asset_formatter(formatter: AssetClass):
    return formats.get(formatter, "{}")


def format_asset_amount(num: Decimal, formatter: AssetClass):
    python_format = get_asset_formatter(formatter)
    return python_format.format(num)


def ensure_positive(amount):
    """Guarantee incoming input is a positive number.

    :raise ValueError: Instead of assert always raise hard ValueError
    """
    if amount <= 0:
        raise ValueError("Needs positive amount")
