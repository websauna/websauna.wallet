from pyramid.config import Configurator
from websauna.system import Initializer
from websauna.utils.autoevent import after
from websauna.utils.autoevent import before
from websauna.utils.autoevent import bind_events

from websauna.system.model.utils import attach_models_to_base_from_module



class AddonInitializer:
    """Configure this addon for websauna.

    If the application wants to customize the addon behavior, it can subclass this class, override methods and bypass the default ``includeme()`` call.
    """

    def __init__(self, config: Configurator):
        self.config = config

    @after(Initializer.configure_templates)
    def configure_templates(self):
        """Include our package templates folder in Jinja 2 configuration."""
        self.config.add_jinja2_search_path('websauna.wallet:templates', name='.html', prepend=False)  # HTML templates for pages
        self.config.add_jinja2_search_path('websauna.wallet:templates', name='.txt', prepend=False)  # .txt templates for SMS

        self.config.include("websauna.wallet.templatevars")

    @after(Initializer.configure_instrumented_models)
    def configure_instrumented_models(self):
        """Plug models from this addon to Websauna."""
        from . import models
        from websauna.system.model.meta import Base

        # Load all models (if we have any) and attach them to SQLALchemy default base class
        # attach_models_to_base_from_module(models, Base)

    @after(Initializer.configure_model_admins)
    def configure_model_admins(self):
        from . import admins
        from . import panels
        from .adminviews import other
        from .adminviews import asset
        self.config.scan(admins)
        self.config.scan(other)
        self.config.scan(asset)
        self.config.scan(panels)

    @after(Initializer.configure_views)
    def configure_views(self):
        self.config.add_route('wallet', '/wallet/*traverse', factory="websauna.wallet.views.wallet.route_factory")
        self.config.add_route('network', '/network/*traverse', factory="websauna.wallet.views.network.route_factory")

        from . import views
        self.config.scan(views)

    @after(Initializer.configure_tasks)
    def configure_tasks(self):
        from . import tasks
        self.config.scan(tasks)

    def configure_events(self):
        from . import subscribers
        from . import starterassets
        self.config.scan(subscribers)
        self.config.scan(starterassets)

    def configure_assets(self):
        pass

    def run(self):
        # We override this method, so that we route home to our home screen, not Websauna default one
        bind_events(self.config.registry.initializer, self)

        self.configure_events()
        self.configure_assets()


def includeme(config: Configurator):
    addon_initializer = AddonInitializer(config)
    addon_initializer.run()





