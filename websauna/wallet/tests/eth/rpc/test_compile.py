from websauna.wallet.ethereum import compiler

def test_compile_sol():
    """See we can get compiled contracts for wallets and tokens."""

    contracts = compiler.compile()
    assert "CrowdfundToken" in contracts