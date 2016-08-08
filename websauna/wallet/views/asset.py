from uuid import UUID

from pyramid import httpexceptions
from pyramid.view import view_config
from slugify import slugify

from websauna.system.core.root import Root
from websauna.system.core.traversal import Resource
from websauna.system.http import Request
from websauna.utils.slug import slug_to_uuid, uuid_to_slug
from websauna.wallet.models import Asset



def asset_to_slug(asset: Asset):
    return "{}-{}".format(slugify(asset.name), uuid_to_slug(asset.id))


def slug_to_asset_id(slug: str) -> UUID:
    *seo, slug = slug.split("-")
    return slug_to_uuid(slug)


class AssetDescription(Resource):

    def __init__(self, request: Request, asset: Asset):
        super(AssetDescription, self).__init__(request)
        self.asset = asset


class AssetFolder(Resource):

    def __getitem__(self, slug: str):
        id = slug_to_asset_id(slug)
        asset = self.request.dbsession.query(Asset).filter_by(id=id).one_or_none()
        if not asset:
            raise KeyError()

        return self.get_description(asset)

    def get_description(self, asset: Asset):
        asset_desc = AssetDescription(self.request, asset)
        return Resource.make_lineage(self, asset_desc, asset_to_slug(asset))


@view_config(context=AssetFolder, route_name="asset", name="")
def asset_root(wallet_root, request):
    return httpexceptions.HTTPNotFound()


@view_config(context=AssetDescription, route_name="asset", name="", renderer="asset/asset.html")
def asset(asset_desc: AssetDescription, request: Request):
    return locals()


def route_factory(request):
    """Set up __parent__ and __name__ pointers required for traversal."""
    asset_root = AssetFolder(request)
    root = Root.root_factory(request)
    return Resource.make_lineage(root, asset_root, "asset")


def get_asset_resource(request, asset: Asset) -> AssetDescription:
    """Build a link to asset page."""
    asset_root = route_factory(request)
    return asset_root.get_description(asset)
