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

"""Helper functions for enabling/disabling logging.

Each module should establish a _LOG global as follows:

  import log_utils
  ...
  _LOG = log_utils.getLogger('messagerecall.xxxx')

To enable DEBUG messages:
-modify the argument to setLevel() from logging.INFO to logging.DEBUG.
"""

import logging


def GetLogger(module_tag, log_level=logging.DEBUG):
  """Helper module to establish application-common logging settings.

  Args:
    module_tag: String reflecting the module logging the message.
    log_level: Allow one-off customization of logging per module.

  Returns:
    logging.Logger object used for logging messages.
  """
  logger = logging.getLogger(module_tag)
  logger.setLevel(log_level)
  return logger
