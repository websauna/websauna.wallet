import transaction
from websauna.wallet.models import AssetNetwork
from websauna.wallet.models import AssetClass


def test_get_or_create_network_asset(dbsession):
    """We should upsert asset by name."""

    with transaction.manager:

        network = AssetNetwork(name="Foo Bank")
        dbsession.add(network)
        dbsession.flush()

        asset = network.get_or_create_asset_by_name("Footoken")
        asset.asset_class = AssetClass.token
        dbsession.flush()
        aid = asset.id

    with transaction.manager:
        network = dbsession.query(AssetNetwork).first()
        asset = network.get_or_create_asset_by_name("Footoken")
        assert asset.id == aid

