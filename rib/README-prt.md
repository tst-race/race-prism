# Prism RIB Toolkit

Requires Python 3.8.

## Installing Manually

In the top-level directory, do:
```bash
python3.8 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e .
pip install -e rib/
```

Once installed, you can run `prt` from anywhere inside the venv.

## Installing on Bastion (automatic)

From a local installation, run

```bash
prt aws setup-bastion --host <bastion_ip> --user <username> --identity <path to private key file>
```

This will create a venv in your home directory on Bastion, install `prt` in that venv,
and add a line to .bashrc to source it.

## PRISM Monitor

The `prt mon` command runs our monitoring script. Important flags:

* `--clients` and `--servers` are necessary on Bastion if EFS is not available, to inform PRT of the client/server count.
* `--replay` will turn on analysis of package latency and drops.
* `prt -v mon` will turn on more verbose output

On Bastion with large deployments, you may run into open file limits. If so, run

```bash
ulimit -n 8192
```

## Sending Messages

On Bastion without EFS, set the environment variable `PRT_CLIENT_COUNT` to the number of clients in the deployment.

`prt send`

Will send a single 140 character message between a random pair of clients.

* `--count N` sends N messages.
* `--delay S` sets the delay between multiple sends. Defaults to 1 second.
* `--sender N` and `--receiver N` fix the sender and/or receiver to be a specific client.
* `--size X` sets the message size in bytes.
* `--text "blah blah blah"` will send a specific plaintext message.

## Inspecting logs

`prt log` is a handy command for inspecting logs.

Examples:

* `prt log c1` will open the PRISM log for Client 1 in `less`
* `prt log s5` will open the PRISM log for Server 5 in `less`
* `prt log -f s10r` will follow the `race.log` for Server 10 with `tail -f`

Full documentation for shorthand options is available in `prt log --help`.