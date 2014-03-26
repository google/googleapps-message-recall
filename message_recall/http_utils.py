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

"""Helper functions and constants for http API requests."""

import httplib2

import log_utils


_EXTENDED_SOCKET_TIMEOUT_S = 10  # Default of 5s seems too short for Admin SDK.
_LOG = log_utils.GetLogger('messagerecall.http_utils')


def GetHttpObject():
  """Helper to abstract Http connection acquisition.

  Not infrequently seeing 'HTTPException: Deadline exceeded...' error when
  running in a scaled environment with > 900 users.  Adding
  _EXTENDED_SOCKET_TIMEOUT_S seems to mostly resolve this.

  Returns:
    Http connection object.
  """
  return httplib2.Http(timeout=_EXTENDED_SOCKET_TIMEOUT_S)
