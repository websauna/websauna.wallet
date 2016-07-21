"""Test token transfers between initial issuer and hosted wallet. """
import pytest

# How many ETH we move for test transactiosn
from websauna.wallet.tests.eth.utils import wait_tx, create_contract_listener


@pytest.mark.slow
def test_deploy_token_contract(client, token):
    """See that we get token contract to blockchain and can read back its public values."""
    
    assert token.version().decode("utf-8") == "v1"
    assert token.totalSupply() == 10000
    assert token.name().decode("utf-8") == "Mootoken"
    assert token.symbol().decode("utf-8") == "MOO"


@pytest.mark.slow
def test_event_receive_tokens(client, hosted_wallet, token, coinbase):
    """A hosted wallet receive tokens."""

    listener, events = create_contract_listener(token)

    txid = token.transfer(hosted_wallet.address, 4000)
    wait_tx(client, txid)
    update_count = listener.poll()

    # Check the transfer event arrives
    assert update_count == 1
    assert len(events) == 1
    event_name, input_data = events[0]
    assert event_name == "Transfer"
    assert input_data["value"] == 4000
    assert input_data["from"] == coinbase
    assert input_data["to"] == hosted_wallet.address

    # Check balances
    token.balanceOf(coinbase) == 6000
    token.balanceOf(hosted_wallet.address) == 400


@pytest.mark.slow
def test_event_send_tokens(client, hosted_wallet, token, coinbase):
    """Hosted wallet sends tokens."""

    # Top up hosted wallet with tokens
    txid = token.transfer(hosted_wallet.address, 4000)
    wait_tx(client, txid)

    # Prepare event listener
    listener, events = create_contract_listener(token)
    listener.poll()

    # Transfer tokens back
    # Do a withdraw from wallet
    txid = hosted_wallet.execute(token, "transfer", args=[coinbase, 4000])
    wait_tx(client, txid)
    update_count = listener.poll()

    # Check the transfer event arrives
    assert update_count == 1
    assert len(events) == 1
    event_name, input_data = events[0]
    assert event_name == "Transfer"
    assert input_data["value"] == 4000
    assert input_data["to"] == coinbase
    assert input_data["from"] == hosted_wallet.address

    # Check balances
    token.balanceOf(coinbase) == 10000
    token.balanceOf(hosted_wallet.address) == 0

