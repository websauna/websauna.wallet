
/** For unit testing accepting data payloads */

contract DecodeData {

    // This value is set by the unit test and then read back to
    // see that calls between contracts work
    bytes public data;
    uint public value;

    function() {
        data = msg.data;
        value = msg.value;
    }
}