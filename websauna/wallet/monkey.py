import transaction


def force_threading_local_transaction_manager():
    """Fix transaction manager threading.local conflict between stdlib and gevent.

    See

    """

    from _thread import _local

    class StdlibThreadLocalTransactionManager(transaction.TransactionManager, _local):
        pass

    transaction.manager = StdlibThreadLocalTransactionManager()