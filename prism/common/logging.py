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
import logging
from logging.config import dictConfig
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog

MONITOR_STATUS = 'prism.monitor'
MPC_LOG = 'prism.mpc'

pre_chain = [
    # Add the log level and producer to the event_dict if the log entry is not from structlog.
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
]

config_dict = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s,%(msecs)06d - [%(levelname)-7s][%(threadName)-12.12s] : %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'prism-formatter': {
            '()': structlog.stdlib.ProcessorFormatter,
            'processor': structlog.dev.ConsoleRenderer(colors=False),
            'foreign_pre_chain': pre_chain,
        },
        'jsonformatter': {
            '()': structlog.stdlib.ProcessorFormatter,
            'processor': structlog.processors.JSONRenderer(),
            'foreign_pre_chain': pre_chain,
        },
    },
    'handlers': {
        'structlog-console': {
            'level': 'INFO',
            'formatter': 'prism-formatter',
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stdout',  # Default is stderr
        },
        'nullhandler': {
            'level': 'DEBUG',
            'class': 'logging.NullHandler',
        },
    },
    'loggers': {
        'prism': {
            'handlers': ['structlog-console'],
            'level': 'DEBUG',
            'propagate': False
        },
        MPC_LOG: {
            'handlers': ['nullhandler'],
            'level': 'DEBUG',
            'propagate': False,
        },
        MONITOR_STATUS: {
            'handlers': ['nullhandler'],
            'level': 'DEBUG',
            'propagate': False
        }
    },
}


def init_logging():
    # now configure logging:
    dictConfig(config_dict)
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.StackInfoRenderer(),  # Include the stack when stack_info=True
            structlog.processors.format_exc_info,  # Include the exception when exc_info=True
            structlog.processors.UnicodeDecoder(),  # Decodes the unicode values in any kv pairs
            structlog.processors.TimeStamper(fmt='%Y-%m-%d %H:%M:%S,%f'),
            # this must be the last one if further customizing formats below...
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    logger = structlog.get_logger("prism")
    logger.info(f"Initialized logging for prism")


def configure_logging(name: str, configuration):
    # set up logging levels and centralized logging:
    logger = structlog.get_logger("prism")
    # allow logging to file from configuration:
    log_dir = configuration.get('log_dir')
    if log_dir:
        configure_log_files(name, logger, configuration)
        disable_console_logging(logger)

    if configuration.get("log_color", False):
        for handler in logger.handlers:
            if handler.name == "structlog-console":
                handler.formatter.processor = structlog.dev.ConsoleRenderer(colors=True)

    # adjust levels of all handlers:
    level = logging.DEBUG if configuration.debug else logging.INFO
    for handler in logger.handlers:
        handler.setLevel(level)


def configure_log_files(name, logger, configuration):
    log_dir = Path(configuration.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    max_bytes = configuration.log_rotate_bytes

    add_file_handler(logger, log_dir / f"prism.log", False, max_bytes)

    monitor_logger = structlog.get_logger(MONITOR_STATUS)
    add_file_handler(monitor_logger, log_dir / f"{name}.monitor.log", True, max_bytes)

    if configuration.debug_extra:
        mpc_logger = structlog.get_logger(MPC_LOG)
        add_file_handler(mpc_logger, log_dir / "mpc.log", True, max_bytes)


def add_file_handler(logger, path: Path, json: bool, max_bytes: int):
    file_handler = RotatingFileHandler(filename=path,
                                       mode="w",
                                       maxBytes=max_bytes,
                                       backupCount=3)

    if json:
        file_handler.setFormatter(structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(sort_keys=True)))
    else:
        file_handler.setFormatter(structlog.stdlib.ProcessorFormatter(
            processor=structlog.dev.ConsoleRenderer(colors=False)))
    logger.addHandler(file_handler)


def disable_console_logging(logger):
    logger.handlers = [handler for handler in logger.handlers if handler.name != "structlog-console"]


def get_logger(name: str, **kwargs):
    return structlog.get_logger(name).bind(**kwargs)
