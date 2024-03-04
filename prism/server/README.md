# README for PRISM Server


## Overview

We are supporting various modes of running the PRISM server:

1. Run single PRISM server from command line
2. Dockerized PRISM server
3. Composing docker images

## Requirements

Prism Server requires Python 3.7 or higher. 
As Homebrew on Mac OS X now made the switch to link `python@3` against Python 3.9, if we wanted 
to downgrade we have to take extra pre-caution to select the correct Python minor version.

Build the `prism` binary per `../README.md` instructions.

## Single server from command line

Without any additional settings, the server will start in OFF mode:

    (venv)$ prism server

To configure an EMIX, use:

    (venv)$ PRISM_ROLE=EMIX prism server

In order to debug a single server, you can also use the entry point into the server Python module like so:

We assume you have a whiteboard running at http://localhost:8080/.  If not, you can skip it or use 
a deployed one like https://wb1.race.cse.sri.com/ 

To run a PRISM Server from this directory as a Python module:

    (venv) $ WHITEBOARDS=http://localhost:8080 PRISM_ROLE=EMIX python -m prism.server

or

    (venv) $ PRISM_ROLE=DROPBOX PRISM_DB_INDEX=0 python -m prism.server

To specify a different configurations as JSON files:

    (venv) $ python -m prism.server <PATH TO CONFIG FILE> [<ANOTHER CONFIG FILE>]


## Unit test PRISM Server

This mode is useful when developing low-level functions in the server architecture.  However, we depend on 
a few packages specifically for unit testing, so install:

    (venv) $ cd tests
    (venv) $ pip install -r requirements.txt

Use the `pytest` unit test framework either in your IDE (PyCharm Community Edition or similar) or 
directly with Python 3: 

    (venv) $ pytest -v  # runs all unit tests that are not marked as skipping 
    (venv) $ pytest test_mixes.py  # runs specific file

## Local Integration Tests

Follow the instructions in `../integration-tests/README.md`.
   




### OLD INSTRUCTIONS 

## Dockerized PRISM Server

The dockerized PRISM servers do not need the Python virtual environment.  You can safely `deactivate` it.

Optionally build while bringing Docker up:

    $ ROLE=DROPBOX ID=test.dropbox docker-compose up [--build] [-d]

Note, the command `docker-compose` without `-f` will actually load the configurations from both 
standard files, `docker-compose.yml` and `docker-compose.override.yml`.

To bring everything properly down, use CTRL-C to interrupt (if not running with `-d`) and then:

    $ docker-compose down

When testing the capability to log to file, use bind-mounting like so to run just a single Docker container:

    $ ./build.sh
    $ docker run -it --rm -e LOG_FILE=/tmp/prism-server.log -v ~/tmp/:/tmp prism-server
    ...
    <CTRL-C>

### Turning Down Chatter from `docker-compose`

When manually running an integration test, it is often beneficial to turn down the chatter of the client and 
whiteboard components, like so.  We have to turn off coloring in order to match the beginning of the line with `grep`:

    $ docker-compose -f integration-tests/base.json --no-ansi up | grep "^prism-server"
