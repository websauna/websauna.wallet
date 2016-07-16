/**
 * Simple hosted wallet contract.
 */
contract Wallet {

    event Deposit(address from, uint value);
    event Withdraw(address to, uint value);
    event Execute(address to, uint value, bytes data);

    address owner;

    function Wallet() {
        owner = msg.sender;
    }

    /**
     * Simple withdrawal operation.
     */
    function withdraw(address _to, uint _value) {
        if(msg.sender != owner) {
            throw;
        }

        Withdraw(_to, _value);

        _to.send(_value);
    }

    /**
     * Executes a transaction from this wallet.
     *
     * We call a function in another smart contract and for the gas use value stored on this contract.
     */
    function execute(address _to, uint _value, bytes _data) {

        if(msg.sender != owner) {
            throw;
        }

        Execute(_to, _value, _data);

        // yes - just execute the call.
        _to.call.value(_value)(_data);
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