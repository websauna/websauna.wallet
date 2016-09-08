This is the communit wiki answer (no reputation) for possible attacks and how to protect agaist them. Feel free to update the list. If your contract functions have characteristics matching prerequisites carefully evaluate your function against given advices.


# Call stack attack

Synonyms: Shallow stack attack, stack attack

Prerequisites: Functions uses `send()` or `call()`

Invoking: The attacker manipulates cross-contract call stack to call() to fail by calling contract with stack of 1023.

Protection: Always check return value of a send() and call().

More info

* http://martin.swende.se/blog/Devcon1-and-contract-security.html


# Re-entrancy attack

Synonyms: Race condition

Prerequisites: Functions uses `send()` or `call()`

Invoking: The untrusted called contract calls the same function back, having it in unexpected state. This is how TheDAO was hacked.The attack can be chained over several of functions (cross function race condition).

Protection: Make sure internal state and balance updates in the function are done before `call()` or `send()`

More info

* https://github.com/ConsenSys/smart-contract-best-practices


# DoS with unexpectd throw

Prerequisites: Functions uses `send()` or `call()` with throw following on fail

Invoking: The attacker manipulates the contract state so that `send()` always fails (e.g. refund)

Protection: Prefer pull payment system over `send()`

More info

* https://github.com/ConsenSys/smart-contract-best-practices



# Malicious libraries

Prerequisites: Using an external contract as a library and obtaining it through the registry.

Invoking: Call another contract function through a contract registry (see ``library`` keyword in Solidity).

Protection: Ensure no dynamic parts which can be swapped out in future versions.

* http://martin.swende.se/blog/Devcon1-and-contract-security.html



# Integer overflow

Prerequisites: Function accepts an uint argument with is used in math

Invoking: Sending very big or very negative integer causing the sum calculation to overflow

Protection: Always check the order of values when doing math operations. E.g. https://github.com/Firstbloodio/token/blob/master/smart_contract/FirstBloodToken.sol

More info

* http://ethereum.stackexchange.com/questions/7293/is-it-possible-to-overflow-uints


# Integer division round down

Prerequisites: Payment logic requires division operator /

Invoking: Programmer's error

Protection: Be aware that divisions are always rounded down


# Allocating too small int for arrays

Prerequisites: for loop as for(var i; ...)

Invoking: Programmer's error

Protection: for(uint i; ...)

More info

* http://ethereum.stackexchange.com/a/7298/620


# Loops and gas limit

Prerequisites: Any loop, copy arrays or strings inside the storage. A for loop where contract users can increase the length of the loop. Consider voting scenario loops.

Invoking: The attacker increases the array length or manipulates block gas limit

Protection: Use pull style payment systems. Spread `send()` over multiple transactions and check `msg.gas` limit.

* https://blog.ethereum.org/2016/06/10/smart-contract-security/

* https://github.com/ConsenSys/smart-contract-best-practices



# Fallback function consuming more than the limit of 2300 gas

Prerequisites: A Solidity contract with catch all function() { } to receive generic sends

Invoking: Programmer's error

Protection: 100% test coverage. Make sure your fallback function stays below 2300 gas. Check for all branches of the function using test suite. Don't store anything in fallback function. Don't call contracts or send ethers in fallback function.

More info:

* https://blog.ethereum.org/2016/06/10/smart-contract-security/

* https://github.com/ConsenSys/smart-contract-best-practices



# Prefer `someAddress.send()`` over `someAddress.call.value()``

Prerequisites: Your contract wants to send some balance

Invoking: This is a pre-emptive measure, send has fixed gas limit of 2300 gas that is so low it doesn't allow room for attack

Protection: Always use `send()` instead of `call()` if possible

More:

* https://github.com/ConsenSys/smart-contract-best-practices


# Forced balance update

Prerequisites: Function reads contract total balance and has some logic depending on it

Invoking: selfdestruct(contractaddress) can forcible upgrade its balance

Protection: Don't trust this.balance to stay within given limits

More

* https://github.com/ConsenSys/smart-contract-best-practices



# Transaction-Ordering Dependence

Synonym: TOD

Prerequisites: A bid style market

Invoking: The attacker sees transactions in mempool before they are finalized in blockchain

Protection: Pre-commit schemes

More

* https://github.com/ConsenSys/smart-contract-best-practices


# Resources

* https://github.com/ConsenSys/smart-contract-best-practices

* https://blog.ethereum.org/2016/06/10/smart-contract-security/

