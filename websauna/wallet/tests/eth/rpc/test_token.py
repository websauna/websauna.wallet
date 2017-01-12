"""Test token transfers between initial issuer and hosted wallet. """
import pytest

# How many ETH we move for test transactiosn
from websauna.wallet.ethereum.contract import confirm_transaction
from websauna.wallet.tests.eth.utils import wait_tx, create_contract_listener



@pytest.mark.slow
def test_deploy_token_contract(web3, token):
    """See that we get token contract to blockchain and can read back its public values."""

    contract= token.contract

    assert contract.call().version() == "2"
    assert contract.call().totalSupply() == 10000
    assert contract.call().name() == "Mootoken"
    assert contract.call().symbol() == "MOO"




@pytest.mark.slow
def test_event_receive_tokens(web3, hosted_wallet, token, coinbase):
    """A hosted wallet receive tokens."""

    # BBB
    token = token.contract

    listener, events = create_contract_listener(token)

    txid = token.transact().transfer(hosted_wallet.address, 4000)
    confirm_transaction(web3, txid)
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
    token.call().balanceOf(coinbase) == 6000
    token.call().balanceOf(hosted_wallet.address) == 400


@pytest.mark.slow
def test_event_send_tokens(web3, hosted_wallet, token, coinbase):
    """Hosted wallet sends tokens."""

    # BBB
    token = token.contract
    listener, events = create_contract_listener(token)

    # Top up hosted wallet with tokens
    txid = token.transact().transfer(hosted_wallet.address, 4000)
    # Prepare event listener
    confirm_transaction(web3, txid)
    update_count = listener.poll()
    assert update_count == 1
    assert events[0][0] == "Transfer"  # [('Transfer', {'from': '0x41e76d4aabeb54a90ca67c59374236314ac3ecd4', 'value': 4000, 'to': '0xdde544e991dfb43808e8f1c4a750eaff3cb17ef4'})]

    # Prepare event listener
    listener, events = create_contract_listener(token)
    listener.poll()

    wallet_listener, wallet_events = create_contract_listener(hosted_wallet.contract)

    # Transfer tokens back
    # Do a withdraw from wallet
    txid = hosted_wallet.execute(token, "transfer", args=[coinbase, 4000])
    receipt = confirm_transaction(web3, txid)
    update_count = listener.poll()
    wallet_update_count = wallet_listener.poll()

    # See hosted wallet processed transfer() call
    assert wallet_update_count == 1
    assert wallet_events[0][0] != "FailedExecute"

    # Check the transfer event arrives
    assert update_count == 1
    assert len(events) == 1
    event_name, input_data = events[0]
    assert event_name == "Transfer"
    assert input_data["value"] == 4000
    assert input_data["to"] == coinbase
    assert input_data["from"] == hosted_wallet.address

    # Check balances
    token.call().balanceOf(coinbase) == 10000
    token.call().balanceOf(hosted_wallet.address) == 0

