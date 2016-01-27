A simple cryptocurrency wallet example for Websauna.

Prerequisites
=============

* PostgreSQL

* Redis

Installation
============

Install to a Python virtual environment using pip command in an editable mode.

Example::

    cd wallet  # This is the folder with setup.py file
    virtualenv venv
    source venv/bin/activate

    pip install -e myapp

Running the website
===================

Local development machine
-------------------------

Example (OSX / Homebrew)::

    psql create wallet_dev
    ws-sync-db development.ini
    pserve -c development.ini --reload

Running the test suite
======================

Example::

    # Install testing dependencies
    pip install ".[dev,test]"

    # Create database used for unit testing
    psql create wallet_test

    ws-db-shell wallet_test
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
    quit

    # Run test suite using py.test running
    py.test myapp/tests --ini test.ini

