from typing import Iterable, List, Tuple, Optional
from uuid import UUID

from pyramid import httpexceptions
from pyramid.security import Allow
from sqlalchemy import func

import arrow
import markdown
from jinja2.exceptions import TemplateNotFound
from pyramid.renderers import render
from pyramid.view import view_config
from websauna.system.core.interfaces import IContainer

from websauna.system.core.root import Root
from websauna.system.core.route import simple_route
from websauna.system.core.traversal import Resource
from websauna.system.http import Request
from websauna.utils.slug import slug_to_uuid, uuid_to_slug
from websauna.wallet.ethereum.utils import bin_to_eth_address
from websauna.wallet.interfaces import IAssetDescriptionFactory
from websauna.wallet.models import AssetNetwork
from websauna.wallet.models import CryptoNetworkStatus
from websauna.wallet.models import AssetState
from websauna.system.core.breadcrumbs import get_breadcrumbs

from websauna.wallet.models import Asset
from websauna.wallet.utils import format_asset_amount
from zope.interface import implementer


class AssetDescription(Resource):

    def __init__(self, request: Request, asset: Asset):
        super(AssetDescription, self).__init__(request)
        self.asset = asset

    def __str__(self):
        return "AssetDescription for {}".format(self.asset)

    def __repr__(self):
        return "AssetDescription for {}".format(self.asset)

    @classmethod
    def asset_to_slug(cls, asset: Asset):
        return asset.slug

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
        return slug

    def get_title(self):
        return "{} ({})".format(self.asset.name, self.asset.symbol)

    @property
    def supply(self):
        if self.asset.supply:
            return format_asset_amount(self.asset.supply, self.asset.asset_class)
        else:
            return ""


@implementer(IContainer)
class AssetFolder(Resource):

    def __getitem__(self, slug: str) -> AssetDescription:

        for asset in self.request.dbsession.query(Asset).filter(Asset.network_id==self.get_network().id):
            if asset.slug == slug:
                return self.get_description(asset)

        raise KeyError()

    def items(self):
        for asset_resource in self.get_public_assets():
            yield asset_resource.__name__, asset_resource

    def get_title(self):
        return "Assets"

    def get_network(self) -> AssetNetwork:
        return self.__parent__.network

    def get_description(self, asset: Asset):

        factory = self.request.registry.queryUtility(IAssetDescriptionFactory, default=AssetDescription)
        asset_desc = factory(self.request, asset)

        assert asset.network == self.get_network()
        return Resource.make_lineage(self, asset_desc, AssetDescription.asset_to_slug(asset))

    def get_public_assets(self) -> Iterable[AssetDescription]:
        """List all assets in this folder."""
        network = self.get_network()
        dbsession = self.request.dbsession
        for asset in dbsession.query(Asset).filter_by(network=network, state=AssetState.public).order_by(Asset.name.asc()):
            yield self.get_description(asset)


@implementer(IContainer)
class NetworkDescription(Resource):

    def __init__(self, request: Request, network: AssetNetwork, asset_count=None):
        super(NetworkDescription, self).__init__(request)
        self.network = network

        self.asset_folder = Resource.make_lineage(self, AssetFolder(request), "assets")
        self.asset_count = asset_count

    def items(self):
        yield "assets", self.asset_folder

    def get_title(self):
        human_name = self.network.other_data.get("human_friendly_name")
        if human_name:
            return human_name
        return self.network.name.capitalize()

    def __getitem__(self, item):
        if item == "assets":
            return self.asset_folder
        raise KeyError()


@implementer(IContainer)
class NetworkFolder(Resource):

    __acl__ = [
        (Allow, "group:admin", "manage-content")
    ]

    def get_title(self):
        return "Blockchains"

    def __getitem__(self, slug: str):
        network = self.request.dbsession.query(AssetNetwork).filter_by(name=slug).one_or_none()
        if not network:
            raise KeyError()

        return self.get_description(network)

    def items(self):
        for resource in self.get_public_networks():
            yield resource.__name__, resource

    def get_description(self, network: AssetNetwork, asset_count=None):
        desc = NetworkDescription(self.request, network, asset_count)
        return Resource.make_lineage(self, desc, network.name)

    def get_public_networks(self) -> Iterable[NetworkDescription]:

        networks = self.request.dbsession \
            .query(AssetNetwork, func.count(Asset.id)) \
            .outerjoin(Asset) \
            .filter(Asset.state == AssetState.public) \
            .group_by(AssetNetwork.id) \
            .order_by(func.count(Asset.id).desc())

        for network, asset_count in networks:
            if network.other_data.get("visible", True) and asset_count > 0:
                yield self.get_description(network, asset_count=asset_count)

    def get_all_public_assets(self):
        assets = []
        networks = self.get_public_networks()
        for network in networks:
            assets += network["assets"].get_public_assets()

        assets = sorted(assets, key=lambda asset: asset.get_title().lower())
        return assets

    def get_next_prev_asset(self, asset: Asset) -> Tuple[Optional[AssetDescription], Optional[AssetDescription]]:
        """Get next/prev navigation in public site listing.

        """
        assets = self.get_all_public_assets()

        for idx, a in enumerate(assets):
            if a.asset == asset:
                break
        else:
            return (None, None)

        if idx > 0:
            prev = assets[idx-1]
        else:
            prev = None

        try:
            next = assets[idx+1]
        except IndexError:
            next = None

        return (next, prev)



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
def all_assets(network_folder: NetworkFolder, request):
    assets = network_folder.get_all_public_assets()

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
    return Resource.make_lineage(root, folder, "blockchain")


def get_network_resource(request, network: AssetNetwork) -> NetworkDescription:
    folder = route_factory(request)
    return folder.get_description(network)


def get_asset_resource(request, asset: Asset) -> AssetDescription:
    """Build a link to asset page."""
    network = get_network_resource(request, asset.network)
    return network["assets"].get_description(asset)


def get_asset_resource_by_name(request, name: str) -> AssetDescription:
    """Build a link to asset page."""

    asset = request.dbsession.query(Asset).filter_by(name=name).one_or_none()

    network = get_network_resource(request, asset.network)
    return network["assets"].get_description(asset)
