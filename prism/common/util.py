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
import hashlib
from datetime import datetime, timedelta
from typing import Dict

PREFIX_LENGTH = 8


def bytes_hex_abbrv(bytes_to_render: bytes, length: int = 0) -> str:
    return bytes_to_render.hex()[:(length if length else PREFIX_LENGTH)] if bytes_to_render else 'None'


def is_jpeg(data):
    return (data.startswith(b'\xff\xd8\xff\xe0') or
            data.startswith(b'\xff\xd8\xff\xee'))


def hash_data(data: bytes) -> str:
    sha = hashlib.sha256()
    sha.update(data)
    return sha.hexdigest()


def posix_utc_now():
    return int(datetime.utcnow().timestamp())


def datafy(cls, dct):
    """
    Convert a dictionary into a dataclass, discarding any fields that the dataclass doesn't support so we don't raise
    an exception.
    """
    fields = {k: v for k, v in dct.items() if k in cls.__dataclass_fields__}
    return cls(**fields)


frequency_limit_times: Dict[str, datetime] = {}


def frequency_limit(category: str, limit: timedelta = timedelta(seconds=30)) -> bool:
    """
    Returns True if it hasn't been called with category in the last limit seconds. Useful for error messages that are
    frequently generated and would otherwise fill the logs with spam.

    example usage:

    while True:
        if frequency_limit("category", timedelta(seconds=60):
            thing_you_only_want_to_do_once_per_minute()
        await trio.sleep(0.1)
    """
    global frequency_limit_times
    last_action = frequency_limit_times.get(category, datetime.utcfromtimestamp(0))

    if datetime.utcnow() > last_action + limit:
        frequency_limit_times[category] = datetime.utcnow()
        return True

    return False


def frequency_limit_reset(category: str):
    global frequency_limit_times
    frequency_limit_times[category] = datetime.utcnow()


def frequency_limit_trigger(category: str):
    global frequency_limit_times
    frequency_limit_times[category] = datetime.utcfromtimestamp(0)


def report_error(logger, category, _exception):
    import traceback
    trace = traceback.format_exc()
    logger.error(f"Error in {category}: {trace}")