/**
 * A sample contract that allowes to set a global value for testing purposes.
 *
 * You set the value on one transaction and read back in another.
 *
 */


contract TestContract {

    // This value is set by the unit test and then read back to
    // see that calls between contracts work
    int public value;

    event Received(int value);

    function setValue(int _value) {
        value = _value;
        Received(value);
    }

    function crash() {
        // Test what happens if hosted wallet calls a contract with throw
        throw;
    }

    function() {
        // Shit happened
        // Shit should not happen
        throw;
    }
}