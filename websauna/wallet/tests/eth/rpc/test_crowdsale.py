"""Test token transfers between initial issuer and hosted wallet. """
import pytest

# How many ETH we move for test transactiosn
from decimal import Decimal
from web3.contract import Contract
from eth_utils.currency import to_wei
from websauna.wallet.ethereum.contract import confirm_transaction, TransactionConfirmationError
from websauna.wallet.ethereum.token import Token
from websauna.wallet.ethereum.utils import wei_to_eth
from websauna.wallet.tests.eth.utils import create_contract_listener, send_balance_to_contract

CAP = to_wei(6000, "ether")

MULTISIG = "0x5589C14FbC92A73809fBCfF33Ab40eFc7E8E8467"


@pytest.fixture(scope="module")
def token(web3, coinbase) -> Contract:
    """Deploy a token contract in the blockchain."""

    # signer, multisig, cap
    extra_arguments = [
        coinbase,
        MULTISIG,
        CAP,
        2,  # 2 share per each ETH
        10 ** 18,  # 1 ETH 10**18 wei
    ]
    return Token.create_token(web3, name="Mootoken", supply=0, symbol="MOO", owner=coinbase, extra_arguments=extra_arguments, contract_name="CrowdfundToken")


@pytest.mark.slow
def test_deploy_crowdsale_contract(web3, token):
    """See that we get token contract to blockchain and can read back its public values."""
    contract = token.contract
    assert contract.call().version() == "2"
    assert contract.call().totalSupply() == 0
    assert contract.call().weiRaised() == 0
    assert contract.call().multisig() == MULTISIG.lower()
    assert contract.call().weiCap() == CAP
    assert contract.call().name() == "Mootoken"
    assert contract.call().symbol() == "MOO"


@pytest.mark.slow
def test_fund_crowdsale(web3, hosted_wallet, token):
    """When we fund crowdsale tokens get created."""

    contract = token.contract
    test_fund = Decimal(1000)  # ETH

    listener, events = create_contract_listener(contract)

    contract.call().investorCount() == 0

    txid = send_balance_to_contract(token.contract, test_fund, gas=1000000)
    confirm_transaction(web3, txid)
    update_count = listener.poll()

    # receipt = web3.eth.getTransactionReceipt(txid)
    # print("Gas used by funding is ", receipt["cumulativeGas"])

    # Check the transfer event arrives
    assert update_count == 2  # Buy + Transfer
    assert len(events) == 2
    event_name, input_data = events[0]
    assert event_name == "Buy"
    assert input_data["eth"] == to_wei(test_fund, "ether")
    assert input_data["tokens"] == 2000

    # Check balances
    web3.eth.getBalance(MULTISIG) == to_wei(test_fund * 2, "ether")
    contract.call().weiRaised() == to_wei(test_fund, "ether")
    contract.call().investorCount() == 1


@pytest.mark.slow
def test_cap(web3, hosted_wallet, token, coinbase):
    """Transactions that would exceed cap is rejected."""

    test_fund = wei_to_eth(CAP + 1)

    txid = send_balance_to_contract(token.contract, test_fund, gas=1000000)
    with pytest.raises(TransactionConfirmationError):
        confirm_transaction(web3, txid)

