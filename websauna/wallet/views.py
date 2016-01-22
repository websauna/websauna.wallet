from websauna.system.http import Request
from websauna.system.core.route import simple_route


# Configure a sample view provided by this addon
@simple_route("/example-view", route_name="example", renderer='wallet/example.html', append_slash=False)
def example_view(request:Request):
    """Render site homepage."""
    return {"project": "wallet"}
