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
import structlog


class CommonPKI:
    def __init__(self, config):
        self.logger = structlog.get_logger(__name__ + ' > ' + self.__class__.__name__)
        self.root_cert = None
        # load PRISM Root CA (if configured)
        root_cert_decoded = config.get("pki_root_cert", "")
        if root_cert_decoded:
            try:
                import cryptography
                from prism.common.crypto.x509 import cert_from_json_str
                self.root_cert = cert_from_json_str(root_cert_decoded)
                self.logger.debug(f"Created PRISM Root CA cert from config")
            except:
                self.logger.warning(f"Could not create PRISM Root CA cert from config (perhaps on Android?)")
