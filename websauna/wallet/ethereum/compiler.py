"""Populus contract helpers."""

#: Compiled contracts in in-process memory
import json
import os


_compile_data = None


def compile():
    """Compile all project .sol files and store in-process cache."""
    global _compile_data
    project_dir = os.path.dirname(__file__)  # ASssume appeneded /contracts
    data_file = os.path.join(project_dir, "build", "contracts.json")
    _compile_data = json.load(open(data_file, "rt"))
    return _compile_data


def get_compiled_contract_cached(name: str) -> dict:
    """Return data struct given by solc compiled."""
    global _compile_data

    if not _compile_data:
        compile()

    assert name in _compile_data, "No contract {}. Available: {}".format(name, _compile_data.keys())

    return _compile_data[name]
