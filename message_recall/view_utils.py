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

"""Helper functions for frontend and backend views."""

import datetime

from models import domain_user
from models import error_reason
from models import recall_task
import recall_errors


_BACKEND_ERROR_COUNTER_TAG = 'recall_error'
_RETRIEVAL_STARTED_COUNTER_TAG = 'retrieval_started'
_RETRIEVAL_ENDED_COUNTER_TAG = 'retrieval_ended'


def CreateSafeUserEmailForTaskName(user_email):
  """Tasks have naming rules that exclude '@' and '.'.

  Task names must match: ^[a-zA-Z0-9_-]{1,500}$

  Args:
    user_email: String user email of the task owner.

  Returns:
    String with unacceptable chars swapped.
  """
  return user_email.replace('@', '-AT-').replace('.', '-DOT-')


def FailRecallTask(task_key_id, reason_string, user_email=None,
                   user_key_id=None, raise_exception=False):
  """Common helper when task failures arise.

  Args:
    task_key_id: Int unique id of the parent task.
    reason_string: String explanation to show users.
    user_email: String email address of the user that failed.
    user_key_id: Int unique id of the user entity to update state.
    raise_exception: Boolean; True if exception should be raised.
  """
  error_reason.ErrorReasonModel.AddTaskErrorReason(task_key_id=task_key_id,
                                                   error_reason=reason_string,
                                                   user_email=user_email)
  recall_task.RecallTaskModel.SetTaskState(task_key_id=task_key_id,
                                           new_state=recall_task.TASK_DONE)
  if user_key_id:
    domain_user.DomainUserToCheckModel.SetUserState(
        user_key_id=user_key_id,
        new_state=domain_user.USER_ABORTED)
  if raise_exception:
    raise recall_errors.MessageRecallError(reason_string)


def GetCurrentDateTimeForTaskName():
  """Tasks have naming rules that exclude '@' and '.'.

  Task names must match: ^[a-zA-Z0-9_-]{1,500}$

  Returns:
    String with acceptable rendering of current time.
  """
  return datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')


def GetUserDomain(user_email):
  """Retrieve the domain of a user from an email address.

  Args:
    user_email: String email address of the form user@domain.com.

  Returns:
    String domain of the user.
  """
  return user_email.split('@')[1]


def _MakeCounterName(key_id, tag):
  """Helper to create a sharded Counter name.

  Args:
    key_id: Int unique id (usually a model entity id).
    tag: String tag which hints at the counter purpose.

  Returns:
    String to be used as a sharded Counter name.
  """
  return '%s_%s' % (key_id, tag)


def MakeRetrievalStartedCounterName(key_id):
  """Wrapper to consistently create counter for User Retrieval started tasks.

  Args:
    key_id: Int unique id (usually a model entity id).

  Returns:
    String to be used as a sharded Counter name.
  """
  return _MakeCounterName(key_id, _RETRIEVAL_STARTED_COUNTER_TAG)


def MakeRetrievalEndedCounterName(key_id):
  """Wrapper to consistently create counter for User Retrieval ended tasks.

  Args:
    key_id: Int unique id (usually a model entity id).

  Returns:
    String to be used as a sharded Counter name.
  """
  return _MakeCounterName(key_id, _RETRIEVAL_ENDED_COUNTER_TAG)


def MakeBackendErrorCounterName(key_id):
  """Wrapper to consistently create counter for Backend Errors encountered.

  Args:
    key_id: Int unique id (usually a model entity id).

  Returns:
    String to be used as a sharded Counter name.
  """
  return _MakeCounterName(key_id, _BACKEND_ERROR_COUNTER_TAG)
