/**
 * Simple hosted wallet contract.
 */
contract Wallet {

    // Withdraw events
    event Deposit(address from, uint value);
    event Withdraw(address to, uint value, uint balanceAfter, uint spentGas);
    event ExceededWithdraw(address to, uint value);
    event OutOfGasWithdraw(address to, uint value, uint balanceAfter);

    // Smart contract call events
    event PreExecute(address to, uint value, uint gas);
    event Execute(address to, uint value, uint balanceAfter, uint spentGas);
    event ExceededExecuteWithValue(address to, uint value);
    event FailedExecute(address to, uint value, uint balanceAfter);

    // Who is the owner of this hosted wallet. This is the (coinbase) address or geth node
    // that your server speaks to via RPC
    address owner;

    function Wallet() {
        // Lock down the wallet, so that only our private geth
        // has the owner private key to speak to us
        owner = msg.sender;
    }

    /**
     * Simple withdrawal operation.
     */
    function withdraw(address _to, uint _value) external {

        uint balanceBefore;
        uint balanceAfter;
        bool success;

        if(msg.sender != owner) {
            throw;
        }

        if(_value > this.balance) {
            ExceededWithdraw(_to, _value);
            return;
        }

        balanceBefore = this.balance;
        success = _to.send(_value);
        balanceAfter = this.balance;

        if(success) {
            Withdraw(_to, _value, balanceAfter, (balanceBefore - balanceAfter) - _value);
        } else {
            OutOfGasWithdraw(_to, _value, balanceAfter);
        }
    }

    /**
     * Executes a transaction from this wallet.
     *
     * We call a function in another smart contract and for the gas use value stored on this contract.
     */
    function execute(address _to, uint _value, uint _gas, bytes _data) external {

        uint balanceBefore;
        uint balanceAfter;
        bool success;

        if(msg.sender != owner) {
            throw;
        }

        if(_value > this.balance) {
            ExceededExecuteWithValue(_to, _value);
            return;
        }

        balanceBefore = this.balance;

        // http://ethereum.stackexchange.com/a/2971/620
        if(_value > 0) {
            success = _to.call.value(_value)(_data);
        } else {
            success = _to.call(_data);
        }

        balanceAfter = this.balance;

        if(success) {
            Execute(_to, _value, balanceAfter, (balanceBefore - balanceAfter) - _value);
        } else {
            FailedExecute(_to, _value, balanceAfter);
        }
    }

    /**
     * Somebody sends ETH to this contract address
     */
    function() {
        // just being sent some cash?
        if (msg.value > 0) {
            Deposit(msg.sender, msg.value);
        }
    }

}