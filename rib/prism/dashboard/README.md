# README for ElasticSearch Dashboard 

## Requirements

The RiB deployment must have a Jaeger instance running, which is backed by an Elasticsearch database.

For `prt` to work, we need
```bash
./rib_N.N.N.sh --code=<path-to>/prism-dev/rib --ssh=/Users/linda/.ssh/sri_prism_rangekey
```

### AWS Deployment 

Starting:

```bash
prt aws up
prt aws provision -f  # if up times out or fails
prt aws ip  # if doing `provision -f` 
prt aws setup-bastion
```

```bash
prt create -f
prt up; prt start
```

Sending (on `bastion`):

```bash
ssh bastion
prt send --count=10 --text="Hello RACE World!"
```

Stopping:

```bash
prt stop; prt down
prt aws down
```

## Invoke from Terminal

Outside `prt`, we need to install all requirements (until we merge with top-level `requirements.txt`):
```bash
cd rib/
pip install -r prism/dashboard/requirements.txt
```

When the RiB or AWS Deployment has been started, you can invoke it directly using Python:

```bash
python -m prism.dashboard -h
python -m prism.dashboard [--gui] \
  --start-time=$(cat ~/.race/rib/prism-rib-tools/LAST_STARTED) --host=$(cat ~/.race/rib/prism-rib-tools/ES_IP) \
  2> /dev/null
```

To prevent the annoying ES warnings about lacking security, use bash redirect like so:
```bash
python -m prism.dashboard ... 2> /dev/null
```

### Setting up for AWS Deployments

Since RiB 2.3.4 (or 2.4.0?), there is the option to split bastion and cluster managing hosts, so make sure you get the IP 
address that refers to `cluster-manager` as it may be different than BASTION.
```bash
export ES_IP=<cluster-manager>
export START=$(( $(date '+%s%N') / 1000000))
python -m prism.dashboard --host $ES_IP --start-time=$START [--gui] [--sleeps 10 10 10 15 0 30] 2> /dev/null
```

Also, if driving `prt aws` from one machine, but running ES Dashboard and Jaeger browsing from a
different machine, obtain your public IP address (e.g., https://whatismyipaddress.com/) and then create a new rule in 
the AWS Console:
1. Log into AWS Console and go to EC2
2. Under "Network & Security" section, select "Security Groups"
3. Select "race-<aws deploment name>-ManagementGlobalAccessSecurityGroup" and in the lower tab, select tab "Inbound rules"
4. Click "Edit inbound rules", then "Add rule" buttons
5. Allow "All traffic" from a Custom entry with your IP address slash 32.
6. Click "Save rules"
