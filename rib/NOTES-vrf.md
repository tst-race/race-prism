# NOTES on Using Cryptographic Sortition in RiB Configurations

## Settings

To enable this mode for role sortition, override these parameters, for example:

```
Parameter overrides:
  sortition = VRF
  server.vrf_p_off = 0.1
  server.vrf_p_emix = 0.25
  server.vrf_n_ranges = 4
  server.vrf_m_replicas = 2
```

These settings are sensitive to the number of servers in a deployment.  The above numbers work well for about 50 
servers.  Calibration experiments can help tuning these parameters for different deployment sizes and experimentation 
goals.

Testing VRF Topology (ER) and 2x50:
```
Parameter overrides:
  sortition = VRF
  server.vrf_p_off = 0.05
  server.vrf_p_emix = 0.25
  server.vrf_n_ranges = 4
  server.vrf_m_replicas = 2
  server.vrf_b_db_emix = 0
```

For N=100 servers, we are working with:
```
Parameter overrides:
  sortition = VRF
  server.vrf_p_off = 0.05
  server.vrf_p_emix = 0.3
  server.vrf_n_ranges = 4
  server.vrf_m_replicas = 2
```

And for N=1000 (VRF Experiments reported at PI Meeting in May 2022):

```
Parameter overrides:
  sortition = VRF
  server.vrf_p_off = 0.1
  server.vrf_p_emix = 0.2
  server.vrf_n_ranges = 20
  server.vrf_m_replicas = 4
  server.vrf_b_db_emix = 4
```

The config generation is part of the `prt create` flow or can be initiated with
```
prt co -v
```
After changing code in `prism/config` use `prt hf` first to update the container.

## Configuring S2S Topology 

We now use `vrf_b_db_emix` to denote three ways of generating a server-to-server topology with direct, bidirectional, 
unicast links.  If this value is `< 0` then (at genesis time) we invoke the old clustering algorithm.  For values 
`>= 0` we allow for two different approaches to randomized topologies that will also come to play in epoch 
switching later.  A second parameter `vrf_c_p_factor` allows for improving connectivity by multiplying the 
probabilities used in random selections of links.

### `server.vrf_b_db_emix == 0`

This induces an Erdos-Renyi (ER) random graph between all EMIX and DROPBOX leaders.  The probability of a link between 
two nodes (sorted by smaller -> larger name or pseudonym to account for undirectedness) is then 

    p = c * ln(n)/n   with n = |{EMIX or DROPBOX leader population}|

### `server.vrf_b_db_emix > 0`

Typical are values 1, 2, 3 in our scenarios.  This number decides to how many EMIXes each DROPBOX leader gets 
connected to. First, we start with a simple, regular ring lattice (k = 2) to connect all EMIXes using the natural 
sorted order of their names/pseudonyms.  Then, each EMIX decides based on its position in the list of all EMIXes 
sorted, with what probability it connects to higher-ordered EMIXes that are not neighbors on the ring.  We propose 
this as a first idea to calculate the link probability for EMIX i (1 <= i <= #EMIX):

    p_i = c * ln(n)/(n * i)


## Pseudonym Ranges (N) and Replicas (M)

Before cryptographic sortition, we assigned each Single-Server Dropbox or MPC Dropbox Committee a running, unique 
`db_index` value to indicate to the clients what non-overlapping range in the pseudonym space to use.  Now, with 
sortition, we allow _M_ replicas for each of the _N_ ranges.  If the setting `server.vrf_db_index_from_range_id` is 
True (default) we only use these _N_ values of the ranges for the `db_index` setting and if _M_ > 1, the replicas 
get used automatically as we force `prism.dropboxes_per_client = 1` then.  A WARNING message is printed during 
configuration if the user also overrides `prism.dropboxes_per_client` to something larger than one, as these settings 
conflict.  If the user sets `server.vrf_db_index_from_range_id = False` then we spread all `db_index` values over the 
range `[0; N * M - 1]` and the clients must then pick the appropriate scalar DROPBOX index.

## Further Performance Enhancements

Once the sortition has successfully completed (we are running it up to `vrf_config_attempts = 5` by default times), we 
could implement additional performance enhancements such as not adding links to non-viable MPC Committees, such as 
`DROPBOX_1_2` in this run for a 2x10 deployment:
```
 ~~~ VRF Step 4: Sortition (attempt #2 of 5) = {'DROPBOX_1_1': 4, 'DROPBOX_1_2': 3, 'EMIX': 2, 'OFF': 0}
```
or even excluding the higher numbered party IDs > 3 in overstocked committees, such as `party_id in {4,5}` of 
`DROPBOX_1_2` here:
```
 ~~~ VRF Step 4: Sortition (attempt #1 of 5) = {'DROPBOX_1_1': 2, 'DROPBOX_1_2': 6, 'EMIX': 1, 'OFF': 0}
```

## Debugging Topology Creation

List MPC committees by server JSON:
```bash
find ~/.race/rib/deployments/aws/vrf10x50aws/configs/ta1/prism -name "race-server-*.json" -print -exec jq .committee_members {} \;
```

Role distribution:
```
$ find ~/.race/rib/deployments/local/vrf250x100/configs/ta1/prism -name "race-server-*.json" -exec jq .role {} \; | sort | uniq -c
      1 "CLIENT_REGISTRATION"
     28 "DROPBOX_LF"
     39 "DUMMY"
     32 "EMIX"
```

Statically connected clients to EMIXes:
```
# get overview of distribution:
$ find ~/.race/rib/deployments/local/vrf250x100/configs/ta1/prism -name committee.json -path "*/race-server-*" \
  -exec jq '.reachableClients | length' {} \; | grep -ve "^0" | sort -n | uniq -c
      1 7
      1 8
      1 9
      2 10
      3 13
      3 14
      2 15
      3 16
      4 17
      5 18
      3 19
      2 20
      1 21
      1 23

# confirming that we have 32 EMIXes:
$ find ~/.race/rib/deployments/local/vrf250x100/configs/ta1/prism -name committee.json -path "*/race-server-*" \
  -exec jq '.reachableClients | length' {} \; | grep -ve "^0" | wc -l
32

# summing up all counts:
$ find ~/.race/rib/deployments/local/vrf250x100/configs/ta1/prism -name committee.json -path "*/race-server-*" \
  -exec jq '.reachableClients | length' {} \; | grep -ve "^0" | paste -sd+ - | bc
502
```

