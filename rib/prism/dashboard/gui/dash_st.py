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
from dataclasses import dataclass, field
import datetime as dt
import graphviz
import json
import math
from natsort import natsorted
import numpy as np  # np mean, np random
import pandas as pd
from plotly.colors import n_colors
import plotly.graph_objects as go
import requests
import streamlit as st
import time
from typing import *

TIC_TIME = 3  # how many seconds to sleep between checking for updates in backend
DEFAULT_BACKEND = "http://0.0.0.0:23456"
DEFAULT_EPOCH = "genesis"


@dataclass(frozen=False, order=True)
class Node:
    shorthand: str
    pseudonym_abbrv: str
    startTimeMillis: int
    role: str = "CLIENT"
    # epoch: str = ""
    dropbox_index: int = -1
    party_id: int = -1
    peers: List[str] = field(default_factory=list)
    dead_since_ms = 0


@dataclass(frozen=False)
class Edge:
    src: str
    dst: str
    epoch: str
    connectionType: str
    startTimeMillis: int
    linkType: str = "unknown link type"
    link_id: str = "unknown link ID"
    personas: str = "unknown personas"


@dataclass(frozen=False)
class NetworkStats:
    up_since: float
    n_clients: int
    n_registration: int
    n_servers: int
    n_valid_servers: int
    role_distribution: Dict[str, int]
    client_out_degs: Dict[str, int]
    server_out_degs: Dict[str, int]
    server_avg_degree: float
    server_max_degree: int
    server_diameter: int
    missing: List[Tuple[str, int]]
    clients: List = None
    reg_nodes: List = None
    servers: List = None
    edges: List = None
    comms: str = None

    def __str__(self):
        return f"Role Distribution: {[f'{r}: {l}' for r, l in self.role_distribution.items()]}\n" + \
            f"Overall directed graph (DIRECT links only = server network):\n" + \
            f"  avg. out-degree = {self.server_avg_degree:.1f}\n" + \
            f"  max. out-degree = {self.server_max_degree}\n" + \
            f"  diameter = {self.server_diameter}"


@dataclass(frozen=False)
class SendReceiveStats:
    n_sent: int
    previous_n_sent: int
    n_matched: int
    previous_n_matched: int
    avg_latency: float
    percentile_50th: float
    percentile_90th: float
    idx: int
    x_latencies: List[int]
    y_latencies: List[float]

    def __str__(self):
        return f"===\n{self.n_matched}/{self.n_sent} Messages Matched " + \
               f"({math.floor(self.n_matched / self.n_sent * 100)}%)\n" + \
               f"Average latency: {self.avg_latency:.2f}s\n" + \
               f"50th percentile: {self.percentile_50th:.2f}s\n" + \
               f"90th percentile: {self.percentile_90th:.2f}s\n" + \
               f"\nFound rank for avg={self.avg_latency:.2f}s at {self.idx} (={(self.idx + 1) * 5}th percentile)\n" + \
               f"Y Latencies: {self.y_latencies}\n"


@dataclass(frozen=False)
class DatabaseStats:
    n_lsp_servers: int
    n_valid_servers: int
    lsp_sizes: List[int]
    flood_sizes: List[int]
    valid_sizes: List[int]

    def __str__(self):
        avg_lsp_table_str = f"Average LSP table size: {sum(self.lsp_sizes)/len(self.lsp_sizes):.2f} / " + \
                            f"{self.n_lsp_servers - 1}\n" if len(self.lsp_sizes) > 0 else ""
        avg_flood_str = f"Average Flood DB size: {sum(self.flood_sizes)/len(self.flood_sizes):.2f} / " + \
                        f"{self.n_lsp_servers}\n" if len(self.flood_sizes) > 0 else ""
        avg_valid_str = f"Average known servers: {sum(self.valid_sizes)/len(self.valid_sizes):.1f} / " + \
                        f"{self.n_valid_servers}\n" if len(self.valid_sizes) > 0 else ""
        return f"{avg_lsp_table_str}{avg_flood_str}{avg_valid_str}"


def format_delta(delta: dt.timedelta) -> str:
    hours, rem = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    return f'{(hours + 24*delta.days):02d}:{minutes:02d}:{seconds:02d}'


st.set_page_config(
    page_title="PRISM ElasticSearch Dashboard",
    page_icon="🌈",
    layout="wide",
)
#st.title("PRISM ElasticSearch Dashboard")


def default_backend():
    st.session_state["backend"] = DEFAULT_BACKEND


def clear_backend():
    st.session_state["backend"] = ""


def clear_ballons():
    st.session_state["balloons"] = ""  # keep track of first balloon's to avoid celebratory overload


def saw_ballons():
    st.session_state["balloons"] = "shown"


backend_URL = st.sidebar.text_input('Fetch PRISM data from:', key="backend", placeholder=DEFAULT_BACKEND)
st.sidebar.button("Use default URL", on_click=default_backend)
# st.sidebar.button("Clear URL", on_click=clear_backend)

epoch_text = st.sidebar.text_input('Filter some data for this epoch:',
                                   value=DEFAULT_EPOCH, autocomplete=DEFAULT_EPOCH, placeholder=DEFAULT_EPOCH)

show_graph = st.sidebar.checkbox('Show topology as graph', False)
show_clients = st.sidebar.checkbox('Show clients in graph', True)
show_regs = st.sidebar.checkbox('Show registration committee in graph', True)
show_dummies = st.sidebar.checkbox('Show DUMMY servers in graph', True)

limit_tables = st.sidebar.slider('Limit tables to this length (0 = no limit)',
                                 min_value=0, max_value=20, step=5, value=0)

message_text = st.sidebar.text_input('Filter for these messages:')

up_since = 0
jaeger_ip = "<no Jaeger IP>"

placeholder = st.empty()
with placeholder.container():
    initial_widget = st.empty()
    uptime_widget = st.empty()
    db_sizes_widget = st.empty()
    topology_widget = st.empty()
    send_receive_widget = st.empty()
    with st.expander(f"Latencies (all epochs) and Transmission Details for epoch = {epoch_text}", expanded=False):
        latencies_widget = st.empty()
    poll_request_widget = st.empty()
    transmissions_widget = st.empty()
    network_widget = st.empty()


def safe_get_json(req: str) -> Optional[Dict]:
    try:  # tolerate requests.exceptions.ConnectionError here!
        response = requests.get(req)
        if 'application/json' not in response.headers.get('Content-Type'):
            return None
        try:
            return response.json()
        except json.decoder.JSONDecodeError:
            return None
    except requests.exceptions.ConnectionError:
        return None


def render_list(list_to_render: List[str], max: int = 3) -> str:
    return f"[{','.join(list_to_render[0:max])}{'...' if len(list_to_render) > max else ''}]"


def deployment() -> bool:
    network_json = safe_get_json(f"{backend_URL}/data/NetworkQuery?epoch={epoch_text}" +
                                 f"&show_graph={str(show_graph).lower()}")
    if not network_json:
        return False
    stats = NetworkStats(**network_json)

    global up_since
    up_since = stats.up_since

    with initial_widget.container():
        st.markdown(f"## {stats.n_clients} clients " +
                    (f"x {stats.n_registration} reg. committee " if stats.n_registration else "") +
                    f"x {stats.n_servers} servers (epoch = {epoch_text})\n")
        if stats.comms:
            st.text(stats.comms)

    with topology_widget.container():
        with st.expander(f"Current Topology for epoch = {epoch_text}", expanded=True):
            if show_graph:
                clients = {c['shorthand']: Node(**c) for c in stats.clients}
                registrations = {r['shorthand']: Node(**r) for r in stats.reg_nodes}
                servers = {s['shorthand']: Node(**s) for s in stats.servers}
                edges = {(e['src'], e['dst']): Edge(**e) for e in stats.edges}
                missing = {sh for sh, _ in stats.missing}
                # mapping for missing fill colors:
                # fillcolor=6 => fillcolor=5
                # fillcolor=7 => fillcolor=4
                # fillcolor=8 => fillcolor=3
                # fillcolor=9 => fillcolor=2
                graph = graphviz.Digraph(node_attr={'colorscheme': 'rdbu11'})
                # start with nodes:
                node_set = set()
                graph.attr('node', shape='circle', style="filled,bold", fillcolor="11", fontcolor="6")
                if show_clients:
                    with graph.subgraph() as client_subg:
                        client_subg.attr(rank='same')
                        for client in clients.keys():
                            if client in missing:
                                client_subg.node(client, fillcolor="1")
                            else:
                                client_subg.node(client)
                            node_set.add(client)
                if show_regs:
                    with graph.subgraph() as reg_subg:
                        reg_subg.attr(rank='same')
                        for reg_server in registrations.keys():
                            if reg_server in missing:
                                reg_subg.node(reg_server, fillcolor="1")
                            else:
                                reg_subg.node(reg_server, fillcolor="#578975")  # X11: aquamarine4
                            node_set.add(reg_server)
                graph.attr('node', shape='box', fontcolor="black")
                for server in servers.values():
                    style = "filled,bold"
                    if server.role == 'EMIX':
                        fillcolor = "2" if server.shorthand in missing else "9"
                    elif server.role in ['DUMMY', "CLIENT_REGISTRATION"] or server.party_id < 0:
                        if not show_dummies:
                            continue
                        fillcolor = "5" if server.shorthand in missing else "white"
                        style = "filled"
                    # now only DROPBOX* left:
                    elif server.party_id == 0:
                        subg_fillcolor = "6"
                        if server.shorthand in missing:
                            fillcolor = "3"
                            subg_fillcolor = "5"  # MPC committee is defunct
                        else:
                            fillcolor = "8"
                            if len(set(server.peers) - missing) < 2:
                                subg_fillcolor = "5"  # MPC committee is defunct
                        with graph.subgraph(name=f"cluster_{server.shorthand}",
                                            graph_attr={"colorscheme": "rdbu11",
                                                        "style": "filled",
                                                        "fillcolor": subg_fillcolor,
                                                        }) as subg:
                            for peer in server.peers:
                                subg.node(peer, style="filled", fillcolor="4" if peer in missing else "7")
                                node_set.add(peer)
                    elif server.party_id > 0:
                        continue  # already added to subgraph for leader
                    else:  # unknown!
                        fillcolor = "brown"
                        style = "filled"
                    graph.node(server.shorthand, style=style, fillcolor=fillcolor)
                    node_set.add(server.shorthand)
                # now add edges:
                for (ss, sd), edge in edges.items():
                    if ss not in node_set or sd not in node_set:
                        continue  # skip edges to hidden nodes
                    if (sd, ss) in edges and ss > sd:
                        continue
                    graph.edge(ss, sd, style="dashed" if edge.connectionType.endswith('INDIRECT') else "solid",
                               dir="none" if (sd, ss) in edges else "forward")
                st.graphviz_chart(graph)
            else:
                with st.container():
                    if stats.missing:
                        st.text(f"{len(stats.missing)} missing nodes:\n  "
                                + "\n  ".join(f"{sh} -> last seen " +
                                              f"{dt.datetime.fromtimestamp(last_seen / 1000).strftime('%m-%d %H:%M:%S')}"
                                              for sh, last_seen in natsorted(stats.missing))
                                + "\n\n")
                    st.text(str(stats))
                    first_column, second_column = st.columns(2)
                    with first_column:
                        st.plotly_chart(plot_degrees(stats.client_out_degs, "Client"))
                    with second_column:
                        st.plotly_chart(plot_degrees(stats.server_out_degs, "Server",
                                                     max=stats.server_max_degree,
                                                     avg=stats.server_avg_degree))
    return True


def db_sizes():
    stats = safe_get_json(f"{backend_URL}/data/DatabasesQuery?epoch={epoch_text}")
    if stats is None:
        return False
    with db_sizes_widget.container():
        if len(stats) == 0:
            st.text(f"<No database sizes yet for epoch = {epoch_text}>")
            return True
        st.text(str(DatabaseStats(**stats)))
    return True


def plot_degrees(xys: Dict[str, int], node_type: str, max: int = 0, avg: float = 0):
    if max:
        xs = [str(d) for d in range(1, max + 1)]
    else:
        xs = list(xys.keys())
    ys = [xys.get(x, 0) for x in xs]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(x=xs,
               y=ys,
               name=f"Out-Degree",
               marker=dict(color="darkblue"),
               showlegend=True,
               # marker_color='darkblue',
               ))
    if avg:
        fig.add_trace(
            go.Scatter(x=[xs[0], xs[-1]], y=[avg, avg],
                       mode='lines',
                       line=dict(color='crimson', width=2),
                       name='Avg. Out-Degree',
                       ))
    fig.update_layout(
        # yaxis_title=f"Number of {node_type}s with Out-Degree",
        xaxis_title=f"Out-Degree {'(direct) ' if node_type.startswith('S') else ''}of {node_type}s",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1,
            xanchor="right",
            x=1,
        ),
        showlegend=node_type.startswith('S'),
        bargap=0.15,  # gap between bars of adjacent location coordinates.
    )
    return fig


def plot_latencies(x: List[int], y: List[float], rank: int, avg: float):
    colors = ['darkblue', ] * len(x)
    if rank in range(len(colors)):
        colors[rank] = 'crimson'

    fig = go.Figure()
    fig.add_trace(
        go.Bar(x=x, y=y,
               name="Latency",
               # marker=dict(color="darkgray"),
               showlegend=True,
               marker_color=colors,
               ))
    fig.add_trace(
        go.Scatter(x=[x[0], x[-1]], y=[avg, avg],
                   mode='lines',
                   line=dict(color='crimson', width=2),
                   name='Avg. Latency',
                   ))
    fig.update_layout(
        yaxis_title="Latency [s]",
        # yaxis2=dict(
        #     tickmode='array',
        #     tickvals=[avg],
        #     tickfont=dict(
        #         color="crimson"
        #     ),
        #     overlaying="y",
        #     side="left",
        #     position=0
        # ),
        xaxis_title='Percentiles [%]',
        legend=dict(
            x=0,
            y=1.0,
            bgcolor='rgba(255, 255, 255, 0)',
            bordercolor='rgba(255, 255, 255, 0)'
        ),
        bargap=0.15,  # gap between bars of adjacent location coordinates.
    )
    return fig


def plot_timeseries(pd_latencies, delivered_, missing_, stored_):
    fig = go.Figure()
    # TODO: or we can label outliers with trace IDs/hyperlinks?  see: https://stackoverflow.com/a/71875960/3816489
    fig.add_trace(
        go.Scatter(
            x=pd_latencies[delivered_]['startTime'],
            y=pd_latencies[delivered_]['latency'],
            name='Delivered Messages',
            mode='markers',
            error_y=dict(
                type='data',
                symmetric=False,
                arrayminus=pd_latencies[delivered_]['latency'],
                array=[0] * len(pd_latencies[delivered_]['latency']),
                width=0
            ),
            marker=dict(
                size=10,
                color='darkblue'
            ),
            hovertemplate='latency = %{y:.2f}s<br>%{text}',
            text=[f"<a href=\"http://{jaeger_ip}:16686/trace/{trace}\">{trace}</a>"
                  for trace in pd_latencies[delivered_].index.tolist()],
        ))
    fig.add_trace(
        go.Scatter(
            x=pd_latencies[stored_]['startTime'],
            y=pd_latencies[stored_]['storedLatency'],
            name='Stored Messages',
            mode='markers',
            error_y=dict(
                type='data',
                symmetric=False,
                arrayminus=pd_latencies[stored_]['storedLatency'],
                array=[0] * len(pd_latencies[stored_]['storedLatency']),
                width=0
            ),
            marker=dict(
                size=10,
                color='plum'
            ),
            hovertemplate='stored after = %{y:.2f}s<br>%{text}',
            text=[f"<a href=\"http://{jaeger_ip}:16686/trace/{trace}\">{trace}</a>"
                  for trace in pd_latencies[stored_].index.tolist()],
        ))
    fig.add_trace(
        go.Scatter(
            x=pd_latencies[missing_]['startTime'],
            y=pd_latencies[missing_]['latency'],
            name='Missing Messages',
            mode='markers',
            marker=dict(
                size=10,
                color='crimson'
            ),
            hovertemplate='%{text}',
            text=[f"<a href=\"http://{jaeger_ip}:16686/trace/{trace}\">{trace}</a>"
                  for trace in pd_latencies[missing_].index.tolist()],
        ))
    # TODO: second plot for latency == 0 in crimson
    fig.update_layout(
        xaxis_title="Sent Time",
        yaxis_title="Latency [s]",
        # hovermode="y unified",
        hoverlabel=dict(
            bgcolor="white",
            font_size=14,
        )
    )
    return fig


def send_receive():
    stats = safe_get_json(f"{backend_URL}/data/SendReceiveQuery?epoch={epoch_text}")  #&cleartext={message_text}")
    if not stats:
        return False

    ts_epoch = stats.pop("ts")
    srs = SendReceiveStats(**stats)

    with send_receive_widget.container():
        recv, div1, sent, div2, success, _, _, _, _, _ = st.columns(10)
        recv.metric("Received", srs.n_matched,
                    delta=srs.n_matched - srs.previous_n_matched if srs.previous_n_matched else None)
        div1.markdown("## /")
        sent.metric("Sent", srs.n_sent,
                    delta=srs.n_sent - srs.previous_n_sent if srs.previous_n_sent else None)
        div2.markdown("## =")
        current_success = math.floor(srs.n_matched / srs.n_sent * 100)
        delta_success_str = None
        delta_success_num = 0
        if srs.previous_n_sent * srs.previous_n_matched:
            delta_success_num = current_success - math.floor(srs.previous_n_matched / srs.previous_n_sent * 100)
            delta_success_str = f"{delta_success_num}%"
        success.metric("Success", f"{current_success}%", delta=delta_success_str)
        if current_success >= 100 and delta_success_num != 0:
            st.balloons()  # celebrate!
        #     if st.session_state.get("balloons", "") == "":
        #         saw_ballons()
        # else:
        #     clear_ballons()

        st.text(f"Average latency: {srs.avg_latency:9.2f}s\n" +
                f"50th percentile: {srs.percentile_50th:9.2f}s\n" +
                f"90th percentile: {srs.percentile_90th:9.2f}s")

    with latencies_widget.container():
        first_column, second_column = st.columns(2)
        first_column.plotly_chart(plot_latencies(
            srs.x_latencies,
            srs.y_latencies,
            srs.idx,
            srs.avg_latency))

        # calculate time series:
        if len(ts_epoch) == 0:
            second_column.text(f"No Transmissions in epoch = {epoch_text}")
            return
        pd_latencies = pd.DataFrame.from_dict(ts_epoch, "index")
        filtered_ = pd_latencies['cleartext'].str.contains(message_text)
        if len(pd_latencies[filtered_]) == 0:
            second_column.text(f"No Transmissions with \"{message_text}\" in message in epoch = {epoch_text}")
            return
        pd_latencies = pd_latencies[filtered_]
        pd_latencies['startTime'] = pd.to_datetime(pd_latencies['startTimeMillis'], unit='ms', origin='unix')
        delivered_ = pd_latencies['latency'] > 0
        missing_ = (pd_latencies['latency'] == 0) & (pd_latencies['storedLatency'] == 0)
        stored_ = (pd_latencies['latency'] == 0) & (pd_latencies['storedLatency'] > 0)
        second_column.plotly_chart(plot_timeseries(pd_latencies, delivered_, missing_, stored_))

        with first_column.container():
            if len(pd_latencies[stored_]):
                stored_text = "<br>".join(
                    [f"{row.startTime.strftime('%m-%d %H:%M:%S')} :mantelpiece_clock: " +
                     f"stored after {row.storedLatency:7.2f}s :point_right: " +
                     f"[http://{jaeger_ip}:16686/trace/{row.Index}](http://{jaeger_ip}:16686/trace/{row.Index})"
                     for row in list(pd_latencies[stored_]
                                     .sort_values(by='startTimeMillis')
                                     .loc[:, ['startTime', 'storedLatency', ]]
                                     .itertuples())[:(limit_tables if limit_tables else None)]])
                total_stored = len(pd_latencies[stored_])
                st.markdown(f"## Stored But Not Retrieved Messages " +
                            f"({total_stored if limit_tables == 0 or limit_tables >= total_stored else f'{limit_tables} of {total_stored}'}):\n" +
                            stored_text, unsafe_allow_html=True)
            else:
                st.empty()

        with second_column.container():
            if len(pd_latencies[missing_]):
                missing_text = "<br>".join(
                    [f"{row.startTime.strftime('%m-%d %H:%M:%S')} :mantelpiece_clock: `{row.Index}` :point_right: " +
                     f"[http://{jaeger_ip}:16686/trace/{row.Index}](http://{jaeger_ip}:16686/trace/{row.Index})"
                     for row in list(pd_latencies[missing_]
                                     .sort_values(by='startTimeMillis')
                                     .loc[:, ['startTime', ]]
                                     .itertuples())[:(limit_tables if limit_tables else None)]])
                total_missing = len(pd_latencies[missing_])
                st.markdown(f"## Missing Messages " +
                            f"({total_missing if limit_tables == 0 or limit_tables >= total_missing else f'{limit_tables} of {total_missing}'}):\n" +
                            missing_text, unsafe_allow_html=True)
            else:
                st.empty()
    return True


def plot_transmissions(df):
    # use groupby and a list comprehension to create data
    dfg = df.groupby(by='channel')
    dark_to_light_orange = n_colors('rgb(255, 69, 0)', 'rgb(255, 165, 0))', len(dfg) - 1, colortype='rgb')
    colors = ["orchid"] + dark_to_light_orange
    data = [
        go.Bar(
            name=channel,
            x=dfg['traceID'],
            y=dfg['latency'],
            marker=dict(color=colors[idx]),
        ) for idx, (channel, dfg) in enumerate(dfg)]
    fig = go.Figure(data)
    fig.update_layout(
        yaxis_title="Latency [s]",
        xaxis_title='Trace ID',
        barmode='stack',
    )
    return fig


def plot_poll_requests(pd_prs, received_, missing_, in_transit_):
    fig = go.Figure()
    # TODO: or we can label outliers with trace IDs/hyperlinks?  see: https://stackoverflow.com/a/71875960/3816489
    fig.add_trace(
        go.Scatter(
            x=pd_prs[received_]['startTime'],
            y=pd_prs[received_]['latency'],
            name='Active Poll Requests',
            mode='markers',
            error_y=dict(
                type='data',
                symmetric=False,
                arrayminus=pd_prs[received_]['latency'],
                array=[0] * len(pd_prs[received_]['latency']),
                width=0
            ),
            marker=dict(
                size=10,
                color='darkblue'
            ),
            customdata=np.stack((pd_prs[received_]['n_steps'], pd_prs[received_]['client'],
                                 pd_prs[received_]['dropbox'], pd_prs[received_]['trace_id']), axis=-1),
            hovertemplate='latency = %{y:.2f}s (steps = %{customdata[0]})<br>' +
                          '%{customdata[1]} -> %{customdata[2]}<br>' +
                          f"<a href=\"http://{jaeger_ip}:16686/trace/" + '%{customdata[3]}>%{customdata[3]}</a>',
            # text=[f"<a href=\"http://{jaeger_ip}:16686/trace/{trace}\">{trace}</a>"
            #       for trace in pd_prs[received_].index.tolist()],
        ))
    fig.add_trace(
        go.Scatter(
            x=pd_prs[in_transit_]['startTime'],
            y=pd_prs[in_transit_]['in_transit_latency'],
            name='In-Transit Poll Requests',
            mode='markers',
            error_y=dict(
                type='data',
                symmetric=False,
                arrayminus=pd_prs[in_transit_]['in_transit_latency'],
                array=[0] * len(pd_prs[in_transit_]['in_transit_latency']),
                width=0
            ),
            marker=dict(
                size=10,
                color='plum'
            ),
            customdata=np.stack((pd_prs[in_transit_]['n_steps'], pd_prs[in_transit_]['client'],
                                 pd_prs[in_transit_]['dropbox'], pd_prs[in_transit_]['trace_id']), axis=-1),
            hovertemplate='in transit after = %{y:.2f}s (steps = %{customdata[0]})<br>' +
                          '%{customdata[1]} -> %{customdata[2]}<br>' +
                          f"<a href=\"http://{jaeger_ip}:16686/trace/" + '%{customdata[3]}>%{customdata[3]}</a>',
        ))
    fig.add_trace(
        go.Scatter(
            x=pd_prs[missing_]['startTime'],
            y=pd_prs[missing_]['latency'],
            name='Missing Poll Requests',
            mode='markers',
            marker=dict(
                size=10,
                color='crimson'
            ),
            customdata=np.stack((pd_prs[missing_]['client'], pd_prs[missing_]['dropbox'], pd_prs[missing_]['trace_id']),
                                axis=-1),
            hovertemplate='%{customdata[1]} -> %{customdata[2]}<br>' +
                          f"<a href=\"http://{jaeger_ip}:16686/trace/" + '%{customdata[3]}>%{customdata[3]}</a>',
        ))
    # TODO: second plot for latency == 0 in crimson
    fig.update_layout(
        xaxis_title="Sent Time",
        yaxis_title="Latency [s]",
        # hovermode="y unified",
        hoverlabel=dict(
            bgcolor="white",
            font_size=14,
        )
    )
    return fig


def poll_requests():
    poll_request_dict = safe_get_json(f"{backend_URL}/data/PollRequestsQuery")
    if not poll_request_dict:
        return False

    with poll_request_widget.container():
        with st.expander(f"Active Poll Requests for epoch = {epoch_text}", expanded=True):

            pd_poll_requests = pd.DataFrame.from_dict(poll_request_dict, "index")
            pd_poll_requests.sort_values(by='client', inplace=True)
            pd_poll_requests['startTime'] = pd.to_datetime(pd_poll_requests['start_time_ms'], unit='ms', origin='unix')
            received_ = pd_poll_requests['latency'] > 0
            missing_ = (pd_poll_requests['in_transit_latency'] == 0)
            in_transit_ = (pd_poll_requests['latency'] == 0) & (pd_poll_requests['in_transit_latency'] > 0)
            st.plotly_chart(plot_poll_requests(pd_poll_requests, received_, missing_, in_transit_))

            # st.write(pd_poll_requests.loc[:, ['client', 'dropbox', 'startTime', 'n_steps', 'in_transit_latency']])
            active_ = (pd_poll_requests['in_transit_latency'] > 0) & (pd_poll_requests['epoch'] == epoch_text)
            if len(pd_poll_requests[active_]):
                # see Streamlit emojis: https://streamlit-emoji-shortcodes-streamlit-app-gwckff.streamlitapp.com/
                active_text = "<br>".join(
                    [f"{row.startTime.strftime('%m-%d %H:%M:%S')} | " +
                     f"`{row.client} -> {row.dropbox}` :point_right: " +
                     f"{str.rjust(f'{row.latency:.2f}s (steps = {row.n_steps})', 25)} :mantelpiece_clock: " +
                     f"[http://{jaeger_ip}:16686/trace/{row.Index}](http://{jaeger_ip}:16686/trace/{row.Index})"
                     for row in list(pd_poll_requests[active_]
                                     .sort_values(by=['client', 'start_time_ms'])
                                     .loc[:, ['startTime', 'n_steps', 'latency', 'client', 'dropbox']]
                                     .itertuples())[:(limit_tables if limit_tables else None)]])
                total_active = len(pd_poll_requests[active_])
                st.markdown(f"## Active Poll Requests for epoch = {epoch_text} " +
                            f"({total_active if limit_tables == 0 or limit_tables >= total_active else f'{limit_tables } of {total_active}'}):\n" +
                            active_text, unsafe_allow_html=True)

            else:
                st.text(f"No Active Poll Requests for epoch = {epoch_text}")
    return True


if backend_URL:
    last_seqnos = {}
    jaeger_ip = safe_get_json(f"{backend_URL}/jaeger")
    if not jaeger_ip:
        jaeger_ip = "<no Jaeger IP>"
    while True:
        # check if sequence numbers have changed and updates need to be pulled:
        current_seqnos = safe_get_json(f"{backend_URL}/seqnos")
        if current_seqnos is not None:
            for qname, current_seqno in current_seqnos.items():
                query_result = False
                if last_seqnos.get(qname, None) != current_seqno:
                    if qname == "NetworkQuery":
                        query_result = deployment()
                    elif qname == "DatabasesQuery":
                        query_result = db_sizes()
                    elif qname == "SendReceiveQuery":
                        query_result = send_receive()
                    elif qname == "PollRequestsQuery":
                        query_result = poll_requests()
                    elif qname == "BootstrapQuery":
                        pass  # TODO: visualize!
                    else:
                        raise RuntimeError(f"Unknown query name: {qname}")
                if query_result:  # only update if HTTP query was successful...
                    last_seqnos[qname] = current_seqno
        # advance up time (if set):
        if up_since:
            up_since_dt = dt.datetime.fromtimestamp(up_since)
            with uptime_widget.container():
                st.text(f"Up since: {up_since_dt.strftime('%H:%M:%S on %Y-%m-%d')}\n" +
                        f"Up time:  {format_delta(dt.datetime.now() - up_since_dt)}")
        time.sleep(TIC_TIME)
else:
    placeholder.write("Please provide PRISM backend server URL!")
