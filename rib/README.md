**This is a RACE Plugin Repository**

**Plugin type:** TA1
**Performer:** SRI
**Variations:** Python Server, Python Client, Android Client

# Prism RIB Toolkit (PRT)

PRT is our omni-tool for managing everything RACE/RIB related. 
It is installed by creating a Python 3.7+ (recommend at least 3.8 or 3.9) virtual environment at the top level of the 
repo with the necessary requirements installed (see `../README.md`) 

You can then type `prt --help` to get help, or `prt <command> --help` for help on a specific subcommand.

## First-Time Setup

Run `prt rib` to install and run `race-in-the-box`. Inside `race-in-the-box`:

``` shell
rib config init
rib jfrog config
rib aws init
rib docker login
```

## Example - A Simple Test Deployment

With `prt rib` running in another terminal:

``` shell
# Creates a new deployment in prt's registry
prt new test2x6 --size 2x6
# Confirms the existence of the new deployment
prt ls
prt info
# Runs rib deployment create
prt create
# Runs rib deployment up
prt up
# Runs rib deployment start
prt start
# Sends a 140 byte test message between a random pair of clients
prt send
# Launches our terminal-based monitor to check the status of the deployment and see when the message is delivered
prt monitor
# Cleanup
prt stop 
prt down
```
