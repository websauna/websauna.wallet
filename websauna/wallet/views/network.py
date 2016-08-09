from uuid import UUID

from pyramid import httpexceptions

import arrow
from pyramid.renderers import render
from pyramid.view import view_config
from slugify import slugify

from websauna.system.core.root import Root
from websauna.system.core.route import simple_route
from websauna.system.core.traversal import Resource
from websauna.system.http import Request
from websauna.utils.slug import slug_to_uuid, uuid_to_slug
from websauna.wallet.models import AssetNetwork
from websauna.wallet.models import CryptoNetworkStatus
from websauna.system.core.breadcrumbs import get_breadcrumbs

from websauna.wallet.models import Asset


class AssetDescription(Resource):

    def __init__(self, request: Request, asset: Asset):
        super(AssetDescription, self).__init__(request)
        self.asset = asset

    @classmethod
    def asset_to_slug(cls, asset: Asset):
        return "{}.{}".format(slugify(asset.name), uuid_to_slug(asset.id))

    @classmethod
    def slug_to_asset_id(cls, slug: str) -> UUID:
        *seo, slug = slug.split(".")
        return slug_to_uuid(slug)

    def get_title(self):
        return "{} ({})".format(self.asset.name, self.asset.symbol)


class AssetFolder(Resource):

    def __getitem__(self, slug: str):
        id = AssetDescription.slug_to_asset_id(slug)
        asset = self.request.dbsession.query(Asset).filter_by(id=id).one_or_none()
        if not asset:
            raise KeyError()

        return self.get_description(asset)

    def get_title(self):
        return "Assets"

    def get_network(self):
        return self.__parent__.network

    def get_description(self, asset: Asset):
        asset_desc = AssetDescription(self.request, asset)
        assert asset.network == self.get_network()
        return Resource.make_lineage(self, asset_desc, AssetDescription.asset_to_slug(asset))


class NetworkDescription(Resource):

    def __init__(self, request: Request, network: AssetNetwork):
        super(NetworkDescription, self).__init__(request)
        self.network = network

        self.asset_folder = Resource.make_lineage(self, AssetFolder(request), "assets")

    def get_title(self):
        return self.network.name.capitalize()

    def __getitem__(self, item):
        if item == "assets":
            return self.asset_folder
        raise KeyError()


class NetworkFolder(Resource):

    def get_title(self):
        return "Chains"

    def __getitem__(self, slug: str):
        network = self.request.dbsession.query(AssetNetwork).filter_by(name=slug).one_or_none()
        if not network:
            raise KeyError()

        return self.get_description(network)

    def get_description(self, network: AssetNetwork):
        desc = NetworkDescription(self.request, network)
        return Resource.make_lineage(self, desc, network.name)


@view_config(context=AssetFolder, route_name="network", name="")
def asset_root(wallet_root, request):
    return httpexceptions.HTTPNotFound()


@view_config(context=AssetDescription, route_name="network", name="", renderer="network/asset.html")
def asset(asset_desc: AssetDescription, request: Request):
    breadcrumbs = get_breadcrumbs(asset_desc, request)
    return locals()


@view_config(context=NetworkFolder, route_name="network", name="")
def network_root(wallet_root, request):
    return httpexceptions.HTTPFound(request.route_url("home"))


@view_config(context=NetworkDescription, route_name="network", name="", renderer="network/network.html")
def network(network_desc: NetworkDescription, request: Request):

    network = network_desc.network

    status = request.dbsession.query(CryptoNetworkStatus).get(network.id)

    timestamp = arrow.get(status.data["heartbeat"]["timestamp"]).datetime
    network_text = render("network/{}.html".format(network.name), {}, request=request)

    breadcrumbs = get_breadcrumbs(network_desc, request)
    return locals()


def route_factory(request):
    """Set up __parent__ and __name__ pointers required for traversal."""
    folder = NetworkFolder(request)
    root = Root.root_factory(request)
    return Resource.make_lineage(root, folder, "network")


def get_network_resource(request, network: AssetNetwork) -> NetworkDescription:
    folder = route_factory(request)
    return folder.get_description(network)


def get_asset_resource(request, asset: Asset) -> AssetDescription:
    """Build a link to asset page."""
    network = get_network_resource(request, asset.network)
    return network["assets"].get_description(asset)
