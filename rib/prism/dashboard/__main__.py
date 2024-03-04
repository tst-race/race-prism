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
import argparse
import logging
from logging.config import dictConfig
from pathlib import Path
import structlog
import trio

from .dashboard import Dashboard

parser = argparse.ArgumentParser(
    "prism.dashboard",
    description="Query elasticsearch for PRISM Dashboard",
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
)
parser.add_argument("--host", dest="es_host", default="localhost", help="Elasticsearch IP address or host name")
parser.add_argument("--port", dest="es_port", type=int, default=9200,
                    help="Elasticsearch port (if 0 then don't query ES)")
parser.add_argument("--socks5", dest="http_proxy", default="", help="SOCKS5 proxy address (e.g., localhost:9443)")
parser.add_argument("--start-time", metavar="MSECS", type=int, default=0,
                    help="Unless 0, use this lower bound for querying ES for the first time " +
                         "(given as milliseconds since epoch)")
parser.add_argument('--sleeps', dest="es_sleeps", metavar="SECS", type=int, nargs=6, default=[10, 10, 10, 15, 25, 30],
                    help="Seconds for [network, databases, send/receive, poll requests, alive, bootstrap] " +
                         "ES Query Tasks to sleep")
parser.add_argument("--jaeger", dest="jaeger_host", default="", help="Jaeger IP address or host name")
parser.add_argument("--gui", action="store_true", default=False,
                    help="Push updates to graphical dashboard (in browser) instead of writing text to STDOUT")
parser.add_argument("--epoch", dest="epoch", default="genesis", help="Filter some output by this epoch")
parser.add_argument("-l", "--log-file", dest="log_file", type=Path,
                    default=Path.home().joinpath(".prism-dashboard.log.out"),
                    help="Path to log file to use")
parser.add_argument("-v", "--verbose", action="store_true", default=False, help="Be more verbose (in terminal output)")


def main():
    args = parser.parse_args()

    # set up logging to file
    dictConfig({
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'prism-formatter': {
                '()': structlog.stdlib.ProcessorFormatter,
                'processor': structlog.dev.ConsoleRenderer(colors=True),
            },
        },
        'handlers': {
            'structlog-file': {
                'level': 'DEBUG',
                'formatter': 'prism-formatter',
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': args.log_file,
                'mode': 'w',
                'maxBytes': 1000000,
                'backupCount': 3,
            }
        },
        'loggers': {
            'prism': {
                'handlers': ['structlog-file'],
                'level': 'DEBUG',
                'propagate': False
            }
        }
    })
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),  # Include the stack when stack_info=True
            structlog.processors.format_exc_info,  # Include the exception when exc_info=True
            structlog.processors.UnicodeDecoder(),  # Decodes the unicode values in any kv pairs
            structlog.processors.TimeStamper(fmt='%Y-%m-%d %H:%M:%S'),
            # this must be the last one if further customizing formats below...
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    structlog.get_logger("prism").info(f"ARGS = {args}")

    try:
        dashboard = Dashboard(**vars(args))
        trio.run(dashboard.run)
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
