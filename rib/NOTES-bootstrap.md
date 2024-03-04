# NOTES on Using Bootstrapping Comannds

## Requirements

A running `prt` environment (or figure out the `rib deployment ...` commands)

## Settings

When doing `prt edit` for a 5x20 (or similar deployment) configure these settings:

```
    "ibe_shards": 3  # overrides; or omit for value=1
  "bootstrap_client_count": 2
```

## At Runtime

### Before First Bootstrap

To send between all *but* the not-started clients that are waiting for bootstrapping:
```bash
prt send -a -ngt 3  # this is #total_clients - #to_be_bootstrapped
```

You could also send from a randomly chosen, started client to bootstrapping client 4:
```bash
prt send --receiver 4 -ngt 3  # sender will be chosen randomly from 1..3
```

### Initiate Boostrapping

To introduce client 4 via client 2, do:
```bash
prt bootstrap -v c2 c4  # first: introducing client, second: client to be bootstrapped
```

In ES Dashboard, the number of clients should increase by 1.  The graph will include the new client "c4"

TODO: observer other changes?

If you had sent a message to client 4 earlier, it should arrive now.

Now to send messages between all clients that are not waiting, or send messages involving new client 4:
```bash
prt send -a -ngt 4  # now we have 4 clients active
prt send --sender 4 -ngt 4
prt send --receiver 4 -ngt 4
```

After you have introduced the last remaining client (here: "c5") into the network, you can stop using the `-ngt N`
switch with `prt send`.
