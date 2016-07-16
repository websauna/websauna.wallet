def wait_tx(eth_json_rpc, txid):
    try:
        eth_json_rpc.wait_for_transaction(txid, max_wait=90.0)
    except ValueError as e:
        raise ValueError("Could not broadcast transaction {}".format(txid)) from e
