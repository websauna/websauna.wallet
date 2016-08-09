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


class NetworkDescription(Resource):

    def __init__(self, request: Request, network: AssetNetwork):
        super(NetworkDescription, self).__init__(request)
        self.network = network

    def get_title(self):
        return self.network.name.capitalize()


class NetworkFolder(Resource):

    def get_title(self):
        return "Networks"

    def __getitem__(self, slug: str):
        asset = self.request.dbsession.query(AssetNetwork).filter_by(name=slug).one_or_none()
        if not asset:
            raise KeyError()

        return self.get_description(asset)

    def get_description(self, network: AssetNetwork):
        desc = NetworkDescription(self.request, network)
        return Resource.make_lineage(self, desc, network.name)


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
