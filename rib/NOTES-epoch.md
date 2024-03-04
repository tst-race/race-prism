# NOTES on Using Epoch Switching Comannds

## Requirements

A running `prt` environment (or figure out the `rib deployment ...` commands)

## Settings

We currently need these settings:

```
Parameter overrides:
  perload_arks = false
```

## Epoch Lifecycle

Currently, all epoch phases are done manually with a human user observing the state of the deployment using the 
monitor or the ES dashboard.

### New Epoch

To start a new epoch:
```
prt epoch new <name>
```

If using the monitor, invoke it with `prt m --epoch <name>`.  Wait for the flood to complete (the average size of the 
flooding DB is the exact number of servers.)

### Next Step

To advance to the next phase when MPC committees form, the backbone routing network gets established, and the clients 
connect to new Emixes, do:
```
prt epoch next
```

### Stopping Before Another New Epoch

Manually stopping the epoch before moving on to the next.  (Optional?)
```
prt epoch off <name>
```

### Triggering Things

```
prt epoch flood_lsp
prt epoch flood_epoch
prt epoch poll
```

Added `prt epoch config <key> <value>` command, which sets a configuration parameter on every node. 
It uses `ast.literal_eval` to parse the value, so it should be formatted as a Python literal.
