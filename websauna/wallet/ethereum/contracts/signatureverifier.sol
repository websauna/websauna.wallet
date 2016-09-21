/**
 * A sample contract that allowes to set a global value for testing purposes.
 *
 * You set the value on one transaction and read back in another.
 *
 */


contract SignatureVerifier {

    address signer = 0x0a489345f9e9bc5254e18dd14fa7ecfdb2ce5f21;

    // http://solidity.readthedocs.io/en/develop/units-and-global-variables.html?highlight=ecrecover#mathematical-and-cryptographic-functions

    // https://github.com/ethereum/pyethereum/blob/develop/ethereum/tests/test_contracts.py#L1191
    function verify(bytes32 h, uint8 v, bytes32 r, bytes32 s) returns (address recoveredAddress) {
        return ecrecover(h, v, r, s);
    }

    /**
     * Verify that input data as address has been signed using a third party key.
     *
     * data is total 97 bytes, contains packed v, r, s
     *
     * @return true is address was correctly signed
     */
    function verifyData(address inputAddress, bytes data) returns (bool matches) {

        /*
        bytes32 hash = sha256(inputAddress);

        bytes32 inputHash;
        uint8 v;
        bytes[32] memory r;
        bytes[32] memory s;
        uint256 i;

        v = uint8(inputHash[0]);

        // Big endian
        for(i=0; i<32; i++) {
             r[i] = data[i+1];
        }

        for(i=0; i<32; i++) {
            s[i] = data[i+33];
        }

        return verify(hash, v, r, s) == signer;
        */
        return false;
    }
}