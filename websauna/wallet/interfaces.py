from zope.interface import Interface


class IAssetDescriptionFactory(Interface):
    """A factory function for creating AssetDescription instances for views.

    Registered as utility. If not defined use the internal :py:class:`websauna.wallet.views.network.AssetDescription`.

    Takes parameters: (Request, websauna.wallet.models.Asset)
    """