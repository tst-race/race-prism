"""
    Purpose:
        Helper functions for logging using the RaceLog functionality

    If you wish to use this file in your own project, make sure to change the
    plugin name in the logging functions to one specific to your project.
"""

#  Copyright (c) 2023 SRI International.
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

from networkManagerPluginBindings import RaceLog


def logDebug(message):
    """
    Purpose:
        A simplifying wrapper for RaceLog.logDebug
    """
    RaceLog.logDebug(f"SRINM", message, "")


def logInfo(message):
    """
    Purpose:
        A simplifying wrapper for RaceLog.logInfo
    """
    RaceLog.logInfo("SRINM", message, "")


def logWarning(message):
    """
    Purpose:
        A simplifying wrapper for RaceLog.logWarning
    """
    RaceLog.logWarning("SRINM", message, "")


def logError(message):
    """
    Purpose:
        A simplifying wrapper for RaceLog.logError
    """
    RaceLog.logError("SRINM", message, "")