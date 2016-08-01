
/* String encoding functionality tests. */
contract String {

    string public value;
    string public constString = "ToholampiÅÄÖ";

    function String(string _value) {
        value = _value;
    }

    function setValue(string _value) {
        value = _value;
    }

    function getValue() public returns (string result) {
        return value;
    }

}