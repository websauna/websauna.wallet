"""This contains app entry point for running a demo site for this addon or running functional tests for this addon."""
import transaction

import websauna.system
from websauna.wallet.ethereum.ethjsonrpc import get_web3


class Initializer(websauna.system.Initializer):
    """A demo / test app initializer for testing addon websauna.wallet."""

    def include_addons(self):
        """Include this addon in the configuration."""
        self.config.include("websauna.wallet")

    def configure_static(self):
        """Configure static asset serving and cache busting."""
        super(Initializer, self).configure_static()

        self.config.registry.static_asset_policy.add_static_view('wallet-static', 'websauna.wallet:static')

    def run(self):
        super(Initializer, self).run()
        self.config.add_jinja2_search_path('websauna.wallet:demotemplates', name='.html', prepend=True)


def main(global_config, **settings):
    init = Initializer(global_config)
    init.run()
    return init.make_wsgi_app()
