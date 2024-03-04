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
from opensearchpy import OpenSearch as Elasticsearch
from opensearchpy import RequestsHttpConnection as RequestsHttpConnection
from opensearch_dsl import Search, Q
import datetime as dt
import structlog
from typing import *


# from: https://github.com/elastic/elasticsearch-py/issues/275 to deal with SOCKS5 proxies to ES
class MyConnection(RequestsHttpConnection):
    def __init__(self, *args, **kwargs):
        proxies = kwargs.pop('proxies', {})
        super(MyConnection, self).__init__(*args, **kwargs)
        self.session.proxies = proxies


SLICE_INCREMENT = 5000


class ESClientTrioAware:

    def __init__(self, es_address: str, proxy_addr: str):
        self._client = Elasticsearch(
            [es_address],
            timeout=30,
            connection_class=MyConnection,
            proxies={'http': proxy_addr, 'https': proxy_addr} if proxy_addr else {}
        )
        self._logger = structlog.get_logger("prism").bind(addr=es_address)
        self._logger.info(self._client.info())
        self._jaeger_host = es_address.rsplit(':', 1)[0]

    @property
    def jaeger_host(self):
        return self._jaeger_host

    def execute_search(self, current_range: Dict[str, int], source_fields: List[str], query: Q, last_n: int = 0):
        if "startTimeMillis" not in source_fields:
            return []
        if last_n > SLICE_INCREMENT:
            self._logger.warning(f"Requested last N={last_n} that is too large (> {SLICE_INCREMENT} - skipping")
            return []
        s = Search(using=self._client, index="jaeger-span*") \
            .filter("range", startTimeMillis=current_range) \
            .sort(f"{'-' if last_n else ''}startTimeMillis") \
            .source(includes=source_fields) \
            .query(query)
        expected = s.count()
        if expected == 0:
            return []
        if last_n > 0:
            self._logger.debug(f"Returning {last_n} of {expected:6d} results " +
                               f"in ]{dt.datetime.fromtimestamp(current_range['gt'] / 1000)} for Q={query}")
            s = s[:last_n]
            results = [{'id': r.meta.id, **r.to_dict()} for r in s.execute()]
        else:
            self._logger.debug(f"Expecting {expected:6d} results " +
                               f"in ]{dt.datetime.fromtimestamp(current_range['gt']/1000)} for Q={query}")
            slice_start = 0
            results = []
            while slice_start < expected:
                # search slicing from https://github.com/elastic/elasticsearch-dsl-py/issues/737
                s = s[slice_start:min(expected, slice_start + SLICE_INCREMENT)]
                results += [{'id': r.meta.id, **r.to_dict()} for r in s.execute()]
                slice_start += SLICE_INCREMENT
        return sorted(results, key=lambda d: d['startTimeMillis'])
