#!/bin/bash
#
# Copyright (c) 2019-2023 SRI International.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

if [[ $(hostname) != *bastion* ]]; then
  echo "This isn't bastion!"
  exit 1
fi

tar xzf prt.tgz
rm ~/prt.tgz

if [[ $(hostname) == rib-bastion ]]; then
  if ! grep -q PYTHONPATH ~/.bashrc; then
    echo 'alias prt="python3.8 -m prism.ribtools"' >> ~/.bashrc
    echo "export PYTHONPATH=$HOME/tools/" >> ~/.bashrc
    python3.8 -m pip install --user -r $HOME/tools/prism/ribtools/requirements.txt
    echo "source ~/prt_settings.sh" >> ~/.bashrc
  fi
else
  if [ ! -d ~/venv ]; then
    python3.8 -m venv venv
    source ~/venv/bin/activate
    pip install -r tools/prism/ribtools/requirements.txt
    pip install -e tools
    echo "source ~/venv/bin/activate" >> ~/.bashrc
    echo "source ~/prt_settings.sh" >> ~/.bashrc
  fi
fi

if [[ $# -eq 2 ]]; then
  echo "export PRT_CLIENT_COUNT=$1" > ~/prt_settings.sh
  echo "export PRT_SERVER_COUNT=$2" >> ~/prt_settings.sh
fi

rm ~/setup_prt.sh