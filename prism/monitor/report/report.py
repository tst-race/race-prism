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

import math
from datetime import datetime, timedelta, timezone


def human_readable_size(byte_count: int) -> str:
    if byte_count == 0:
        return "0"

    prefixes = ["B", "KiB", "MiB", "GiB", "TiB"]
    magnitude = math.floor(math.log(byte_count, 1024))
    mantissa = float(byte_count) / math.pow(1024, magnitude)
    if magnitude > 0:
        mantissa = f"{mantissa:.2f}"

    if magnitude >= len(prefixes):
        return "TOO MANY"

    return f"{mantissa} {prefixes[magnitude]}"


class Report:
    """Represents a snapshot of the state of the system, and can create a printed summary."""

    # Information about the structure of these dicts can be found in
    # monitor.deployment.Deployment.generate_report()
    deployment_stats: dict
    server_stats: dict
    client_stats: dict
    dropbox_stats: dict
    error_stats: dict
    replay_stats: dict = None

    verbose: bool = False

    def print_report(self):
        self.print_monitor_stats()
        self.print_server_stats()
        # self.print_dropbox_stats()
        print("")
        self.print_client_stats()
        print("")
        self.print_error_stats("client")
        self.print_error_stats("server")

        if self.replay_stats:
            self.print_replay_stats()

    def print_monitor_stats(self):
        stats = self.deployment_stats
        print(
            f"{stats['lines_read']} log lines consumed from "
            f"{stats['client_count']} clients and "
            f"{stats['server_count']} servers.\n"
            f"Epoch = {stats['epoch']}\n"
        )
        now = stats['now']
        beginning = stats['beginning']
        if now != datetime.min.replace(tzinfo=timezone.utc):
            print(f"Last activity: {stats['now']}")
            duration: timedelta = now - beginning
            print(f"Uptime: {duration}")

    def print_server_stats(self):
        self.print_ark_stats()
        self.print_mpc_stats()
        print(f"{self.server_stats['stored']} messages stored.")
        print(f"{self.server_stats['polls']} active poll requests.")
        # if self.verbose:
        #     for server in self.server_stats["stored_servers"]:
        #         print(f"{server.name}: {server.dropbox_stored_count}")

    def print_ark_stats(self):
        stats = self.server_stats["ark"]
        alive = len(self.server_stats["alive"])
        total = self.deployment_stats["server_count"]
        stable = len(stats["stable"])
        arking = len(stats["arking"])

        if alive < total:
            print(f"{alive}/{total} servers alive.")
            if self.verbose:
                print("Dead servers:")
                for server in self.server_stats["dead"][:5]:
                    print(f"  {server.name} (last seen {server.last_activity})")

        print(f"{stable}/{arking} servers stable.")
        if self.verbose and self.server_stats["avg_lsp_table"]:
            print(f"Average LSP table size: {self.server_stats['avg_lsp_table']:.2f} / {alive - 1}")
        if self.verbose and self.server_stats["avg_flood_db"]:
            print(f"Average Flood DB size: {self.server_stats['avg_flood_db']:.2f}")
        if self.verbose:
            if self.server_stats.get('avg_ongoing_floods', 0):
                print(f"Average ongoing floods: {self.server_stats.get('avg_ongoing_floods')}")
            if self.server_stats.get('avg_queued_floods', 0):
                print(f"Average queued floods: {self.server_stats.get('avg_queued_floods')}")
            if self.server_stats.get('triggered_floods'):
                print(f"Total floods: {self.server_stats.get('triggered_floods')}")

        if stats.get("missing"):
            print(f"Average known servers: {stats['average_known']}")
            # print("Unstable servers:")
            # unstable_strs = [f"{server.name} ({len(server.known_servers)})" for server in stats["unstable"]]
            # print(", ".join(unstable_strs))

            # print("Missing servers:")
            # missing_strs = [f"{name} ({count})" for name, count in stats["missing"].items() if count > 0]
            # print(", ".join(missing_strs))

        if stats.get("destabilized"):
            print(f"{len(stats['destabilized'])} servers formerly stable.")
            print(", ".join([server.name for server in stats["destabilized"]]))

    def print_mpc_stats(self):
        stats = self.server_stats["mpc"]

        if stats["servers"]:
            print(f"{len(stats['bootstrapped'])}/{len(stats['servers'])} " f"MPC committees bootstrapped.")

    def print_dropbox_stats(self):
        stats = self.server_stats["dropbox"]
        if not stats:
            return

        if stats["unused"]:
            print(f"{len(stats['unused'])} unused dropboxes: {', '.join(d.name for d in stats['unused'])}")
        if stats["overloaded"]:
            print(f"{len(stats['overloaded'])} overloaded dropboxes: {', '.join(d.name for d in stats['overloaded'])}")

    def print_client_stats(self):
        stats = self.client_stats
        mstats = stats["messages"]

        if stats["dead"]:
            total = stats["alive"] + len(stats["dead"])
            print(f"{stats['alive']}/{total} clients alive")
            if self.verbose:
                print("Dead clients:")
                for client in stats["dead"][:5]:
                    print(f"  {client.name}")
        if stats["alive"]:
            print(f"Clients: {stats['polling']} polling.")
            if stats["backlog"]:
                print(f"{stats['backlog']} message(s) backlogged.")
            if stats["expired_arks"]:
                print(f"{stats['expired_arks']} expired ARKs.")
            if self.verbose:
                arking = len(self.server_stats["ark"]["arking"])
                print(f"Average known servers: {stats['avg_valid_servers']} / {arking}")
                print(f"Average time remaining on ARKs: {stats['average_ttl']:.2f}")
        print(f"{mstats['matched']}/{mstats['sent']} Messages Matched")
        if self.verbose:
            print("Unmatched:")
            for message in mstats["unmatched"][0:5]:
                print(message.trace_id)
        if mstats["avg_latency"]:
            print(f"Average latency: {mstats['avg_latency']:.2f}s")
        if mstats["percentiles"]:
            percentiles_to_print = [5, 9]
            for percentile in percentiles_to_print:
                print(f"{percentile}0th percentile: {mstats['percentiles'][percentile-1]:.2f}s")

    def print_error_stats(self, category: str):
        error_nodes = self.error_stats[category]

        if not error_nodes:
            return

        print(f"{category.capitalize()} Errors:")
        print(", ".join([node.name for node in error_nodes]))
        print("")

    def print_replay_stats(self):
        stats = self.replay_stats

        print("Network")
        print(f"{stats['inflight']} packages in flight.")

        for channel, tstats in stats["channels"].items():
            if channel == "inflight":
                continue

            drop_stats = stats["dropped"][channel]

            print()
            print(f"{channel.capitalize()}: " f"{tstats.count} packages, " f"{human_readable_size(tstats.bytes)}.")
            if tstats.avg_latency:
                latency_ms = tstats.avg_latency / 1000
                print(f"Average latency {latency_ms:.2f}ms")
            if tstats.max_latency:
                latency_ms = tstats.max_latency / 1000
                print(f"Maximum latency: {latency_ms:.2f}ms")
            if drop_stats["latency_percentiles"]:
                percentiles = drop_stats["latency_percentiles"]
                print(f"95th percentile: {percentiles[18] / 1000:.2f}ms")

            # md = [pkg for pkg in stats.get("misdelivered", []) if pkg.channel == channel]
            # if md:
            #     print(f"{len(md)} Misdelivered packages")
            #     for pkg in md[:5]:
            #         pkg: Package
            #         delivered_to = [name for name, _ in pkg.receivers]
            #         print(f"  {pkg.digest[:16]} {pkg.sender} -> {pkg.intended_recipient} delivered to {delivered_to}")

            for threshold, dropped in drop_stats["thresholds"].items():
                if dropped:
                    print(f"Packages sent but not received after {threshold}s: {len(dropped)}")

                if self.verbose and threshold == max(drop_stats["thresholds"].keys()):
                    for pkg in dropped[-5:]:
                        print(f"{pkg.sender}->{pkg.intended_recipient}: {pkg.hexdigest[:16]}, trace: {pkg.trace}")

            if self.verbose and drop_stats["worst_senders"]:
                print(f"{'Worst nodes':40}")
                for node, drops in drop_stats["worst_nodes"].items():
                    print(f"{node}: {drops}")
                print(f"{'Worst senders':40}")
                for sender, drops in drop_stats["worst_senders"].items():
                    print(f"{sender}: {drops}")
                print(f"{'Worst receivers':40}")
                for receiver, drops in drop_stats["worst_receivers"].items():
                    print(f"{receiver}: {drops}")
