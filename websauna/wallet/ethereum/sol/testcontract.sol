/**
 * A sample contract that allowes to set a global value for testing purposes.
 *
 * You set the value on one transaction and read back in another.
 *
 */


contract TestContract {

    public int value;

    function setValue(int _value) {
        value = _value;
    }
}