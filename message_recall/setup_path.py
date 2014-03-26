# Copyright 2014 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""This file establishes the presence of a library folder for dependencies.

These directives allow dependencies to be placed in a lib folder.

Subsequently, attempts to import required packages to give the user guidance
avoiding deployment confusion.
"""

import os
import sys


_MESSAGE_RECALL_DIR = os.path.dirname(os.path.abspath(__file__))


def _SetMessageRecallLibPath(sys_path, message_recall_dir):
  message_recall_lib_dir = os.path.join(message_recall_dir, 'lib')
  if message_recall_lib_dir not in sys_path:
    sys_path.append(message_recall_lib_dir)


_SetMessageRecallLibPath(sys.path, _MESSAGE_RECALL_DIR)


import log_utils  # pylint: disable=g-import-not-at-top


_LOG = log_utils.GetLogger('messagerecall.setup_path')


try:
  # pylint: disable=g-import-not-at-top, unused-import
  import apiclient
  from apiclient.discovery import build
  import httplib2
  import oauth2client
  from oauth2client.tools import run
  from oauth2client.client import SignedJwtAssertionCredentials
  # pylint: enable=g-import-not-at-top, unused-import
except ImportError as e:
  module_package_map = {'apiclient': 'google-api-python-client',
                        'apiclient.discovery': 'google-api-python-client',
                        'oauth2client.tools': 'oauth2client.tools',
                        'oauth2client.client': 'oauth2client.client'}
  # The exception message will be of the form: 'No module named xxxxx'
  failed_module = package_name = str(e).split()[-1]
  if failed_module in module_package_map:
    package_name = module_package_map[failed_module]
  _LOG.error('Unable to find "%s". You are missing the ./lib directory or you '
             'need to install the "%s" package.', failed_module, package_name)
  sys.exit(1)
