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

"""Message Recall Exception classes."""


class Error(Exception):
  """Base class Exception."""
  pass


class MessageRecallError(Error):
  """Base class Exception."""
  pass


class MessageRecallAbortedError(MessageRecallError):
  """Raised when aborting prematurely."""
  pass


class MessageRecallAuthenticationError(MessageRecallError):
  """Any authentication problem."""
  pass


class MessageRecallCounterError(MessageRecallError):
  """Any counter problem."""
  pass


class MessageRecallDataError(MessageRecallError):
  """Any data store problem."""
  pass


class MessageRecallGmailError(MessageRecallError):
  """Problem with accessing Gmail."""
  pass


class MessageRecallInputError(MessageRecallError):
  """Problem with query parameter input."""
  pass


class MessageRecallJsonError(MessageRecallError):
  """Problem with reading/writing json."""
  pass


class MessageRecallMemcacheError(MessageRecallError):
  """Problem with reading/writing memcache."""
  pass


class MessageRecallShutdownError(MessageRecallError):
  """Raised when backend instance getting shutdown by the runtime."""
  pass


class MessageRecallXSRFError(MessageRecallError):
  """Problem with xsrf validation."""
  pass
