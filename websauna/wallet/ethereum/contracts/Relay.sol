// http://ethereum.stackexchange.com/a/190/620
import "Registrar";


/**
 * Registrar based relay contract.
 *
 * Look up the actual contract code from upgradeable registry.
 */
contract Relay {

    public address registrar;
    public string name;

    function Relay(address _registrar, string _name) {
        registrar = registrar;
        name = name;
    }

    function() {
        address currentVersion:
        registrar = Registrar(registrar);
        currentVersion = registrar.addr(name);
        if(!currentVersion.delegatecall(msg.data)) throw;
    }
}