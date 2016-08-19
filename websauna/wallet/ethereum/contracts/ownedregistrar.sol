// See http://ethereum.stackexchange.com/questions/1684/registrar-in-a-private-testnet

// sol OwnedRegistrar
// Global registrar with single authoritative owner.
// @authors:
//   Gav Wood <g@ethdev.com>

import "./owned.sol";
import "./Registrar.sol";


contract OwnedRegistrar is owned {

    event Changed(string indexed name);

	struct Record {
		address addr;
	}

	function currentOwner() returns (address) {
		return owner;
	}

	function disown(string _name) onlyowner {
		delete m_toRecord[_name];
		Changed(_name);
	}

	function setAddr(string _name, address _a) onlyowner {
		m_toRecord[_name].addr = _a;
		Changed(_name);
	}

	function addr(string _name) constant returns (address) { return m_toRecord[_name].addr; }

	mapping (string => Record) m_toRecord;
}