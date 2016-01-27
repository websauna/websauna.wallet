from decimal import Decimal

from websauna.wallet.models import AssetFormat


formats = {
    AssetFormat.fiat: "{:0,.2f}",
}

def get_asset_formatter(formatter: AssetFormat):
    return formats.get(formatter, "{}")


def format_asset_amount(num: Decimal, formatter: AssetFormat):
    python_format = get_asset_formatter(formatter)
    return python_format.format(num)