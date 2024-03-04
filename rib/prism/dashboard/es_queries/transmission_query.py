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
from dataclasses import fields, dataclass, field
import datetime as dt
from networkx import DiGraph, shortest_path, NetworkXNoPath
from opensearch_dsl import Q
import pandas as pd
import re
import trio
from typing import List, Dict

from .es_client import ESClientTrioAware
from .events import ReceiveEvent, Spandata
from .triggered_query import TriggeredQuery


@dataclass(frozen=True)
class TransmissionDetails:
    traceID: str
    startTimeMillis: int
    startTime: dt.datetime
    latency: float
    segments: int
    channel: str = field(default="network-manager")  # Network Manager or Comms-specific


def custom_sorting(col: pd.Series) -> pd.Series:
    """Series is input and ordered series is expected as output"""
    result = col
    # apply custom sorting only to column 'channel':
    if col.name == "channel":
        custom_dict = {}

        # ensure that network-manager is always first, then sort rest alphabetically
        def custom_channel_sort(value):
            return "" if value == "network-manager" else value

        ordered_items = list(col.unique())
        ordered_items.sort(key=custom_channel_sort)
        # apply custom order first:
        for index, item in enumerate(ordered_items):
            custom_dict[item] = index
        result = col.map(custom_dict)
    return result


class TransmissionQuery(TriggeredQuery):

    def __init__(self, es_client: ESClientTrioAware, start_time: int, trigger_ch: trio.MemoryReceiveChannel,
                 verbose: bool = False):
        super().__init__(es_client, start_time, trigger_ch)
        self.verbose = verbose
        self.transmissions = pd.DataFrame(columns=[feld.name for feld in fields(TransmissionDetails)])

    def __str__(self):
        if not self.verbose:
            return ""
        if len(self.transmissions) == 0:
            return f"{__name__}: <No transmissions yet>"
        return f"Transmission Details ({len(self.transmissions)}):\n" + \
               f"{self.transmissions.loc[:, ['traceID', 'startTime', 'latency', 'channel', 'segments']].head(5)}\n"

    def get_data(self, **kwargs):
        if len(self.transmissions) == 0:
            return {}
        return dict(transmissions=self.transmissions.to_dict('index'))

    def process_search_results(self, search_results: List, trigger_element: ReceiveEvent):
        path = DiGraph()
        spandata_list = []
        # targets: span_id's of send events that are potential beginnings of path:
        targets = []  # type: List[str]
        for result in search_results:
            # try to parse Comms channel ID from `sendPackage` events;
            # also collect potential targets from `sendPackage` events if they came from a client
            channel_id = "unknown"
            if result['operationName'] == "sendPackage" and result['process']['serviceName'].startswith("race-"):
                connection_id = [tag["value"] for tag in result['tags'] if tag["key"] == "connectionId"][0]
                try:
                    channel_id = re.search('^(.*)/([^/]*)/LinkID_(.*)$', connection_id).group(2)
                except AttributeError:
                    pass
                if result['process']['serviceName'].startswith("race-client-"):
                    targets.append(result['spanID'])  # keep track of all potential targets from clients
            elif result['operationName'] == "handleReceivedMessage":
                # this allows us to distinguish different batches of the same clear text having been sent:
                message_hash = [tag["value"] for tag in result['tags'] if tag["key"] == "messageHash"][0]
                message_size = int([tag["value"] for tag in result['tags'] if tag["key"] == "messageSize"][0])
            elif result['operationName'] == "sendMessage":
                start_time_millis = int(result["startTimeMillis"])
            # save information from this event for traversing graph and calculating latencies later:
            sd = Spandata(result['spanID'], result['traceID'], int(result['startTimeMillis']), int(result['duration']),
                          result['operationName'], result['process']['serviceName'], channel_id)
            spandata_list.append(sd)
            # build up graph structure for this traceID using any Jaeger references:
            for ref in result.get("references", []):
                if ref.get("refType", "") in ["CHILD_OF", "FOLLOWS_FROM"]:
                    path.add_edge(sd.spanID, ref["spanID"], processName=sd.opName, )
        spandata = pd.DataFrame(spandata_list).set_index(Spandata.get_index())

        # dissect path for transmission details:
        if not path.has_node(trigger_element.root):
            # print(f"Missing source={span_id} in path for traceID={trace_id}")
            return
        shortest = []
        for target in targets:
            if not path.has_node(target):
                # print(f"Missing target={target} in path for traceID={trace_id}")
                return
            try:
                shortest = shortest_path(path, source=trigger_element.root, target=target)
                break  # we found one!
            except NetworkXNoPath:
                pass
        if len(shortest) == 0:
            # print(f"Skipping trace {trace_id} because path is not connected between source={span_id} and targets={
            # targets}!")
            return
        transmission_list = []
        previousTimeMillis = spandata.loc[shortest[0]]['startTimeMillis']
        # the first (network manager) segment starts with the duration (endTime(trace_id) - startTime(shortest[0]):
        network_manager_latency = trigger_element.endTimeMillis - spandata.loc[shortest[0]]['startTimeMillis']
        network_manager_segments = 1
        comms_latency_by_channel = {}  # type: Dict[str, int]  # channel GID -> accumulated latency
        comms_segments_by_channel = {}  # type: Dict[str, int]  # channel GID -> number of segments encountered
        for s_id in shortest[1:]:
            # print(f"{spandata.loc[s_id]}\n")
            # skip most path items; only consider bipartite graph (path) alternating between receive and send:
            if spandata.loc[s_id]['opName'] not in ["receiveEncPkg", "sendPackage"]:
                continue
            # calculate times and accumulate in respective buckets:
            currentTimeMillis = spandata.loc[s_id]['startTimeMillis']
            if spandata.loc[s_id]['opName'] == "receiveEncPkg":
                # border crossing Network Manager -> Comms
                network_manager_latency += (previousTimeMillis - currentTimeMillis)
                network_manager_segments += 1
            if spandata.loc[s_id]['opName'] == "sendPackage":
                # border crossing Comms -> Network Manager: add duration!
                # currentTimeMillis += spandata.loc[s_id]['durationMicro']/1000
                current_latency = comms_latency_by_channel.get(spandata.loc[s_id]['channelID'], 0)
                comms_latency_by_channel[spandata.loc[s_id]['channelID']] = current_latency + \
                                                                          (previousTimeMillis - currentTimeMillis +
                                                                           spandata.loc[s_id]['durationMicro'] / 1000)
                current_segments = comms_segments_by_channel.get(spandata.loc[s_id]['channelID'], 0)
                comms_segments_by_channel[spandata.loc[s_id]['channelID']] = current_segments + 1
            previousTimeMillis = currentTimeMillis
        # comms_latency = sum([latency for latency in comms_latency_by_channel.values()])
        # see last cells for justification to estimate ideal Comms as 1s per segment:
        # comms_estimated_latency = sum([segments for segments in comms_segments_by_channel.values()])
        # self.latencies.loc[trigger_element.traceID, ["network_manager_latency", "comms_latency", "latency", "comms_estimated"]] = \
        #     [network_manager_latency / 1000, comms_latency / 1000, network_manager_latency / 1000 + comms_latency / 1000, comms_estimated_latency]
        # build up list of transmission details for different latency types:
        # Network Manager is default channel:
        transmission_list.append(
            TransmissionDetails(trigger_element.traceID,
                                currentTimeMillis, dt.datetime.fromtimestamp(currentTimeMillis / 1000),
                                network_manager_latency / 1000, network_manager_segments - 2))
        for channel, latency in comms_latency_by_channel.items():
            transmission_list.append(
                TransmissionDetails(trigger_element.traceID,
                                    currentTimeMillis, dt.datetime.fromtimestamp(currentTimeMillis / 1000),
                                    latency / 1000, comms_segments_by_channel[channel], channel))
        to_be_appended = pd.DataFrame(transmission_list).fillna(value=0)
        self.transmissions = pd.concat([self.transmissions, to_be_appended], ignore_index=True)
        # custom sorting of second key, see: https://stackoverflow.com/a/67829348/3816489
        self.transmissions.sort_values(
            by=['startTimeMillis', 'channel'],
            ascending=True,
            inplace=True,
            key=custom_sorting,
        )
        self.current_update_seqno += 1

    async def trigger_loop(self):
        async with self.trigger_ch:
            async for trigger_element in self.trigger_ch:
                assert isinstance(trigger_element, ReceiveEvent)
                if not self.verbose:
                    continue  # skip querying for transmission details
                results = self.es_client.execute_search({"gt": self.last_started},
                                                        Spandata.source_fields(),
                                                        Q("match", traceID=trigger_element.traceID))
                self.process_search_results(results, trigger_element)
