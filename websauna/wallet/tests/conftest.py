# from websauna.tests.conftest import *

# pytest_plugins = "websauna.tests.conftest",


# Populus dependencies and such require this
import gevent.monkey
gevent.monkey.patch_all()