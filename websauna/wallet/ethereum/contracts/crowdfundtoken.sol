contract tokenRecipient { function receiveApproval(address _from, uint256 _value, address _token, bytes _extraData); }

/**
 * Overflow aware uint math functions.
 *
 * Inspired by https://github.com/MakerDAO/maker-otc/blob/master/contracts/simple_market.sol
 */
contract SafeMath {
  //internals

  function safeMul(uint a, uint b) internal returns (uint) {
    uint c = a * b;
    assert(a == 0 || c / a == b);
    return c;
  }

  function safeSub(uint a, uint b) internal returns (uint) {
    assert(b <= a);
    return a - b;
  }

  function safeAdd(uint a, uint b) internal returns (uint) {
    uint c = a + b;
    assert(c>=a && c>=b);
    return c;
  }

  function assert(bool assertion) internal {
    if (!assertion) throw;
  }
}


contract CrowdfundToken is SafeMath {
    /* Public variables of the token */
    string public name;
    string public symbol;
    string public version;

    /** Key that verifies address signatures */
    address public signer;

    /** Account holding crowdfunded funds */
    address public multisig;

    /* Contract owner */
    address public owner;

    uint8 public decimals;
    uint256 public totalSupply;

    /** Maximum allowed funds */
    uint256 public weiCap;

    /* How many ethers we have raised */
    uint256 public weiRaised;

    /* How many unique investors */
    uint256 public investorCount;

    /* How token price is calculated */
    uint256 public priceMultiplier;
    uint256 public priceDivider;

    /* This creates an array with all balances */
    mapping (address => uint256) public balanceOf;
    mapping (address => mapping (address => uint256)) public allowance;
    mapping (address => mapping (address => uint256)) public spentAllowance;

    /* This generates a public event on the blockchain that will notify clients */
    event Transfer(address indexed from, address indexed to, uint256 value);
    event Buy(address indexed sender, uint eth, uint tokens);

    /* Initializes contract with initial supply tokens to the creator of the contract */
    function CrowdfundToken(
        uint256 initialSupply,
        string tokenName,
        uint8 decimalUnits,
        string tokenSymbol,
        string versionOfTheCode,
        address owner_,
        address signer_,
        address multisig_,
        uint256 weiCap_,
        uint256 priceMultiplier_,
        uint256 priceDivider_
        ) {

        balanceOf[owner] = initialSupply;              // Give the creator all initial tokens
        totalSupply = initialSupply;                        // Update total supply
        name = tokenName;                                   // Set the name for display purposes
        symbol = tokenSymbol;                               // Set the symbol for display purposes
        decimals = decimalUnits;                            // Amount of decimals for display purposes
        version = versionOfTheCode;
        signer = signer;
        multisig = multisig_;
        owner = owner_;
        weiCap = weiCap_;
        priceMultiplier = priceMultiplier_;
        priceDivider = priceDivider_;
    }

    /* Send coins */
    function transfer(address _to, uint256 _value) {
        if (balanceOf[msg.sender] < _value) throw;           // Check if the sender has enough
        if (balanceOf[_to] + _value < balanceOf[_to]) throw; // Check for overflows
        balanceOf[msg.sender] -= _value;                     // Subtract from the sender
        balanceOf[_to] += _value;                            // Add the same to the recipient
        Transfer(msg.sender, _to, _value);                   // Notify anyone listening that this transfer took place
    }

    /* Allow another contract to spend some tokens in your behalf */
    function approveAndCall(address _spender, uint256 _value, bytes _extraData)
        returns (bool success) {
        allowance[msg.sender][_spender] = _value;
        tokenRecipient spender = tokenRecipient(_spender);
        spender.receiveApproval(msg.sender, _value, this, _extraData);
        return true;
    }

    /* A contract attempts to get the coins */
    function transferFrom(address _from, address _to, uint256 _value) returns (bool success) {
        if (balanceOf[_from] < _value) throw;                 // Check if the sender has enough
        if (balanceOf[_to] + _value < balanceOf[_to]) throw;  // Check for overflows
        if (spentAllowance[_from][msg.sender] + _value > allowance[_from][msg.sender]) throw;   // Check allowance
        balanceOf[_from] -= _value;                          // Subtract from the sender
        balanceOf[_to] += _value;                            // Add the same to the recipient
        spentAllowance[_from][msg.sender] += _value;
        Transfer(_from, _to, _value);
        return true;
    }

    /** How many tokens get per each wei */
    function calculateTokens(uint256 blockNum, uint256 buyValue) constant returns(uint) {
        return safeMul(buyValue, priceMultiplier) / priceDivider;
    }

    function buy() {

        uint tokens = calculateTokens(block.number, msg.value);

        // Not enough value, could not buy even one token
        if(tokens <= 0) {
            throw;
        }

        // TODO: Add signature check

        address recipient = msg.sender;

        if (safeAdd(weiRaised, msg.value) > weiCap) throw;

        if(balanceOf[recipient] == 0) {
            investorCount += 1;
        }

        balanceOf[recipient] = safeAdd(balanceOf[recipient], tokens);
        totalSupply = safeAdd(totalSupply, tokens);
        weiRaised = safeAdd(weiRaised, msg.value);

        // if (!multisig.send(msg.value)) throw;

        // Initial buy in
        Buy(recipient, msg.value, tokens);

        // ERC-20 compatible update
        Transfer(0, recipient, tokens);
    }

    /**
     * This unnamed function is called whenever someone tries to send ether to it.
     *
     * Tested for gas limit: 104424
     */
    function () {
        buy();
    }
}
