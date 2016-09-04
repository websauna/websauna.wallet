from typing import Iterable
from uuid import UUID

from pyramid import httpexceptions
from sqlalchemy import func

import arrow
import markdown
from jinja2.exceptions import TemplateNotFound
from pyramid.renderers import render
from pyramid.view import view_config
from slugify import slugify

from websauna.system.core.root import Root
from websauna.system.core.route import simple_route
from websauna.system.core.traversal import Resource
from websauna.system.http import Request
from websauna.utils.slug import slug_to_uuid, uuid_to_slug
from websauna.wallet.ethereum.utils import bin_to_eth_address
from websauna.wallet.models import AssetNetwork
from websauna.wallet.models import CryptoNetworkStatus
from websauna.wallet.models import AssetState
from websauna.system.core.breadcrumbs import get_breadcrumbs

from websauna.wallet.models import Asset
from websauna.wallet.utils import format_asset_amount


class AssetDescription(Resource):

    def __init__(self, request: Request, asset: Asset):
        super(AssetDescription, self).__init__(request)
        self.asset = asset

    @classmethod
    def asset_to_slug(cls, asset: Asset):
        return "{}.{}".format(slugify(asset.name), uuid_to_slug(asset.id))

    @property
    def address(self) -> str:
        if self.asset.external_id:
            return bin_to_eth_address(self.asset.external_id)
        else:
            return ""

    @property
    def network(self) -> "NetworkDescription":
        return self.__parent__.__parent__

    @classmethod
    def slug_to_asset_id(cls, slug: str) -> UUID:
        *seo, slug = slug.split(".")
        return slug_to_uuid(slug)

    def get_title(self):
        return "{} ({})".format(self.asset.name, self.asset.symbol)

    @property
    def supply(self):
        if self.asset.supply:
            return format_asset_amount(self.asset.supply, self.asset.asset_class)
        else:
            return ""


class AssetFolder(Resource):

    def __getitem__(self, slug: str):
        id = AssetDescription.slug_to_asset_id(slug)
        asset = self.request.dbsession.query(Asset).filter_by(id=id).one_or_none()
        if not asset:
            raise KeyError()

        return self.get_description(asset)

    def get_title(self):
        return "Assets"

    def get_network(self) -> AssetNetwork:
        return self.__parent__.network

    def get_description(self, asset: Asset):
        asset_desc = AssetDescription(self.request, asset)
        assert asset.network == self.get_network()
        return Resource.make_lineage(self, asset_desc, AssetDescription.asset_to_slug(asset))

    def get_public_assets(self) -> Iterable[AssetDescription]:
        """List all assets in this folder."""
        network = self.get_network()
        dbsession = self.request.dbsession
        for asset in dbsession.query(Asset).filter_by(network=network, state=AssetState.public).order_by(Asset.name.asc()):
            yield self.get_description(asset)


class NetworkDescription(Resource):

    def __init__(self, request: Request, network: AssetNetwork, asset_count=None):
        super(NetworkDescription, self).__init__(request)
        self.network = network

        self.asset_folder = Resource.make_lineage(self, AssetFolder(request), "assets")
        self.asset_count = asset_count

    def get_title(self):
        human_name = self.network.other_data.get("human_friendly_name")
        if human_name:
            return human_name
        return self.network.name.capitalize()

    def __getitem__(self, item):
        if item == "assets":
            return self.asset_folder
        raise KeyError()


class NetworkFolder(Resource):

    def get_title(self):
        return "Blockchains"

    def __getitem__(self, slug: str):
        network = self.request.dbsession.query(AssetNetwork).filter_by(name=slug).one_or_none()
        if not network:
            raise KeyError()

        return self.get_description(network)

    def get_description(self, network: AssetNetwork, asset_count=None):
        desc = NetworkDescription(self.request, network, asset_count)
        return Resource.make_lineage(self, desc, network.name)

    def get_public_networks(self) -> Iterable[NetworkDescription]:

        networks = self.request.dbsession \
            .query(AssetNetwork, func.count(Asset.id)) \
            .outerjoin(Asset) \
            .group_by(AssetNetwork.id) \
            .order_by(func.count(Asset.id).desc())

        for network, asset_count in networks:
            if network.other_data.get("visible", True):
                yield self.get_description(network, asset_count=asset_count)


@view_config(context=AssetFolder, route_name="network", name="", renderer="network/assets.html")
def asset_root(asset_folder, request):
    assets = asset_folder.get_public_assets()
    network_desc = asset_folder.__parent__
    breadcrumbs = get_breadcrumbs(asset_folder, request)
    return locals()


@view_config(context=AssetDescription, route_name="network", name="", renderer="network/asset.html")
def asset(asset_desc: AssetDescription, request: Request):
    breadcrumbs = get_breadcrumbs(asset_desc, request)

    long_description = asset_desc.asset.other_data.get("long_description", "")
    if long_description:
        long_description = markdown.markdown(long_description)

    return locals()


@view_config(context=NetworkFolder, route_name="network", name="", renderer="network/networks.html")
def network_root(network_folder, request):
    networks = network_folder.get_public_networks()

    breadcrumbs = get_breadcrumbs(network_folder, request)

    return locals()


@view_config(context=NetworkFolder, route_name="network", name="all-assets", renderer="network/all_assets.html")
def all_assets(network_folder, request):
    assets = []
    networks = network_folder.get_public_networks()
    for network in networks:
        assets += network["assets"].get_public_assets()

    assets = sorted(assets, key=lambda asset: asset.get_title())

    breadcrumbs = get_breadcrumbs(network_folder, request, current_view_name="All digital assets", current_view_url=request.resource_url(network_folder, "all-assets"))

    return locals()


@view_config(context=NetworkDescription, route_name="network", name="", renderer="network/network.html")
def network(network_desc: NetworkDescription, request: Request):

    network = network_desc.network

    timestamp = ""
    status = request.dbsession.query(CryptoNetworkStatus).get(network.id)

    if status:
        heartbeat = status.data.get("heartbeat")
        if heartbeat:
            timestamp = arrow.get(status.data["heartbeat"]["timestamp"]).datetime

    try:
        network_text = render("network/{}.html".format(network.name), {}, request=request)
    except TemplateNotFound:
        pass

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
