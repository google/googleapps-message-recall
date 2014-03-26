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

"""Database models to track error reasons for reporting."""

import log_utils

from google.appengine.datastore.datastore_query import Cursor
from google.appengine.ext import ndb


_LOG = log_utils.GetLogger('messagerecall.models.error_reason')
_REASON_ROWS_FETCH_PAGE = 20


class ErrorReasonModel(ndb.Model):
  """Model to track errors in the various recall tasks."""

  recall_task_id = ndb.IntegerProperty(required=True)
  user_email = ndb.StringProperty()  # Empty if error before user activities.
  error_datetime = ndb.DateTimeProperty(required=True, auto_now_add=True)
  error_reason = ndb.StringProperty(required=True)  # Max 500 character length.

  @classmethod
  def FetchOneUIPageOfErrorsForTask(cls, task_key_urlsafe, urlsafe_cursor):
    """Utility to query and fetch all error reasons for UI pages.

    Args:
      task_key_urlsafe: String unique id of the task record.
      urlsafe_cursor: String cursor from previous fetch_page() calls.
                      This is a publishable version acquired via '.urlsafe()'.

    Returns:
      Iterable of one page of ErrorReasonModel reasons.
    """
    return cls.GetQueryForAllTaskErrorReasons(
        task_key_id=ndb.Key(urlsafe=task_key_urlsafe).id()).fetch_page(
            _REASON_ROWS_FETCH_PAGE,
            start_cursor=Cursor(urlsafe=urlsafe_cursor))

  @classmethod
  def GetQueryForAllTaskErrorReasons(cls, task_key_id):
    """Prepare a Query object to retrieve all error reasons of a task.

    Args:
      task_key_id: Int unique id of the task record.

    Returns:
      Query object filtered to all error reasons for one task.
    """
    return cls.query(cls.recall_task_id == task_key_id).order(
        cls.error_datetime)

  @classmethod
  def GetErrorReasonCountForTask(cls, task_key_id):
    """Count the #error reasons associated with a task.

    Args:
      task_key_id: Int unique id of the task record.

    Returns:
      Integer number of error reasons associated with the current task.
    """
    return cls.GetQueryForAllTaskErrorReasons(task_key_id=task_key_id).count(
        keys_only=True)

  @classmethod
  def AddTaskErrorReason(cls, task_key_id, error_reason, user_email=None):
    """Add a new error reason entity for a recall task.

    Args:
      task_key_id: Int unique id of the task record.
      error_reason: String reason for an error (<500 characters).
      user_email: [Optional] String with a user email if the error applies
                   to a single user.
    """
    error_reason_entity = cls(
        recall_task_id=task_key_id,
        error_reason=error_reason)
    if user_email:
      error_reason_entity.user_email = user_email
    error_reason_entity.put()
