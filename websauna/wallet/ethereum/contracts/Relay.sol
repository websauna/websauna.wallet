import "./Registrar.sol";

/**
 * Registrar based relay contract.
 *
 * Look up the actual contract code from upgradeable registry.
 *
 * http://ethereum.stackexchange.com/a/190/620
 */
contract Relay {

    address public registrarAddr;
    string public name;

    function Relay(address _registrarAddr, string _name) {
        registrarAddr = _registrarAddr;
        name = _name;
    }

    function getImplAddr() constant returns (address) {
        Registrar registrar = Registrar(registrarAddr);
        return registrar.addr(name);
    }

    function() {
        currentVersion = this.getImplAddr();
        if(!currentVersion.delegatecall(msg.data)) throw;
    }
}