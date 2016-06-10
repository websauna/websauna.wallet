from zope.interface import Interface


class IOperationPerformer(Interface):
    """Marker interface to map SQL models to operations to be performed."""