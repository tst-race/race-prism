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
from prism.config.environment import Range


def generate_test_plan(test_range: Range) -> dict:
    test_delay = 120
    run_time = 600
    return {
        "test-cases": {
            "auto-messages": {
                "enabled": True,
                "period": 10,
                "quantity": 3,
                "size": 140,
            }
        },
        "test-config": {
            "run-time": run_time,
            "test-delay": test_delay,
            "mode": "network-manager",
        },
    }
