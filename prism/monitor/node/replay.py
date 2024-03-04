#  Copyright (c) 2019-2023 SRI International.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

from __future__ import annotations
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple


@dataclass
class Package:
    """Represents a RIB EncPkg whose send/retrieve is recorded in replay.log/receive.log."""

    size: int
    digest: str
    channel: str
    transmission_type: str
    trace: str = field(default=None)
    sender: str = field(default=None)
    intended_recipient: str = field(default=None)
    send_date: datetime = field(default=None)
    receivers: List[Tuple[str, datetime]] = field(default_factory=list)
    duplicate: bool = field(default=False)

    def sent(self, sender: str, send_date: datetime):
        """Marks the package as having been sent."""
        if self.sender:
            self.duplicate = True

        self.sender = sender
        self.send_date = send_date

    def received(self, receiver: str, recv_date: datetime):
        """Marks the package as having been received."""
        self.receivers.append((receiver, recv_date))

    @property
    def latency(self) -> Optional[float]:
        """The time (in microseconds) between when a package was sent and received.
        If this was a multicast, then take the average latency of all receipts."""
        if not self.delivered:
            return None

        return sum(
            [(recv_date - self.send_date) / timedelta(microseconds=1) for (_, recv_date) in self.receivers]
        ) / len(self.receivers)

    @property
    def delivered(self) -> bool:
        return bool(self.send_date and self.receivers)

    @property
    def misdelivered(self) -> bool:
        if not self.delivered:
            return False
        if "*" in self.intended_recipient:
            return False

        for (receiver, _) in self.receivers:
            if receiver == self.intended_recipient:
                return False

        return True

    def dropped(self, now: datetime, threshold: int) -> bool:
        """Checks for packages that were sent, but not received after a specified number of seconds."""
        if not self.send_date:
            return False
        if self.receivers:
            return False

        delta = now - self.send_date

        return delta.total_seconds() > threshold

    @staticmethod
    def from_json(vals: dict) -> Package:
        channel = "unknown"
        if vals["tags"].get("links"):
            channel = vals["tags"]["links"][0].split("/")[1]

        tags = vals["tags"]

        return Package(
            size=vals["size"],
            transmission_type=vals["transmissiontype"],
            digest=tags["hash"],
            trace=tags.get("trace"),
            channel=channel,
        )


@dataclass
class ReplayStats:
    count: int = field(default=0)
    bytes: int = field(default=0)
    total_latency: float = field(default=0.0)
    avg_latency: float = field(default=None)
    max_latency: float = field(default=None)
    latencies: List[float] = field(default_factory=list)


class Replay:
    """Aggregates statistics for sent and recieved Packages."""

    def __init__(self):
        self.packages: Dict[str, Package] = {}

        # Tracks packages that don't have both send/receive events, so we can warn about dropped packages.
        self.undelivered: Dict[str, Package] = {}
        self.last_send = None

        self._stats = {}

    def parse(self, line):
        vals = line.values
        digest = vals["tags"]["hash"]

        pkg = self.packages.get(digest) or Package.from_json(vals)

        if pkg.channel not in self._stats:
            self._stats[pkg.channel] = ReplayStats()

        stats = self._stats[pkg.channel]

        timestamp = datetime.fromisoformat(vals["tags"]["time"])

        if pkg.digest not in self.packages:
            self.packages[digest] = pkg
            stats.count += 1
            stats.bytes += pkg.size
        else:
            # To account for multicast packages, which are received multiple times, subtract the latency from the
            # total before  updating the package with new information, and then add it back in later.
            if pkg.delivered:
                stats.total_latency -= pkg.latency

        if "recvtime" in vals:
            pkg.received(vals["receiver"], timestamp)
            if pkg.delivered and pkg.digest in self.undelivered:
                del self.undelivered[pkg.digest]
        else:
            pkg.sent(vals["sender"], timestamp)
            pkg.intended_recipient = vals["receiver"]
            if not pkg.delivered:
                self.undelivered[pkg.digest] = pkg

            if not self.last_send or timestamp > self.last_send:
                self.last_send = timestamp

        if pkg.delivered:
            stats.total_latency += pkg.latency
            stats.latencies.append(pkg.latency)
            stats.max_latency = max(pkg.latency, stats.max_latency or 0)

        if stats.total_latency > 0 and stats.count:
            stats.avg_latency = stats.total_latency / stats.count

    def stats(self, drop_thresholds):
        stats = {
            "channels": self._stats,
            "inflight": len(self.undelivered),
            "misdelivered": [pkg for pkg in self.packages.values() if pkg.misdelivered],
        }

        drop_stats = {}

        for channel in self._stats.keys():
            threshold_stats = {
                threshold: [
                    pkg
                    for pkg in self.undelivered.values()
                    if pkg.channel == channel and pkg.dropped(self.last_send, threshold)
                ]
                for threshold in drop_thresholds
            }
            max_threshold = max(drop_thresholds)
            max_drops: List[Package] = threshold_stats[max_threshold]
            drop_counts_by_pair = {}
            drop_counts_by_sender = {}
            drop_counts_by_receiver = {}
            drop_counts_by_node = {}

            def dropped(counter: Dict[str, int], name: str):
                counter[name] = counter.get(name, 0) + 1

            def worst(counter: Dict[str, int], n: int = 500):
                worst_names = sorted(counter.keys(), key=lambda s: counter[s], reverse=True)
                return {name: counter[name] for name in worst_names[:n]}

            for drop in max_drops:
                pair = f"{drop.sender}->{drop.intended_recipient}"
                dropped(drop_counts_by_pair, pair)
                dropped(drop_counts_by_sender, drop.sender)
                dropped(drop_counts_by_receiver, drop.intended_recipient)
                dropped(drop_counts_by_node, drop.sender)
                dropped(drop_counts_by_node, drop.intended_recipient)

            worst_pairs = worst(drop_counts_by_pair)
            worst_senders = worst(drop_counts_by_sender)
            worst_receivers = worst(drop_counts_by_receiver)
            worst_nodes = worst(drop_counts_by_node)

            if len(self._stats[channel].latencies) > 10:
                percentiles = statistics.quantiles(self._stats[channel].latencies, n=20, method="inclusive")
            else:
                percentiles = None

            drop_stats[channel] = {
                "thresholds": threshold_stats,
                "latency_percentiles": percentiles,
                "worst_pairs": worst_pairs,
                "worst_senders": worst_senders,
                "worst_receivers": worst_receivers,
                "worst_nodes": worst_nodes,
            }

        stats["dropped"] = drop_stats

        return stats
