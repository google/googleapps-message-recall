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

"""Database models for root Message Recall Task entity."""

import time

import log_utils
from models import domain_user
from models import error_reason
import recall_errors

from google.appengine.datastore.datastore_query import Cursor
from google.appengine.ext import ndb


_GET_ENTITY_RETRIES = 5
_GET_ENTITY_SLEEP_S = 2
_LOG = log_utils.GetLogger('messagerecall.models.recall_task')
_TASK_ROWS_FETCH_PAGE = 10

TASK_STARTED = 'Started'
TASK_GETTING_USERS = 'Getting Users'
TASK_RECALLING = 'Recalling'
TASK_DONE = 'Done'

TASK_STATES = [TASK_STARTED, TASK_GETTING_USERS, TASK_RECALLING, TASK_DONE]


class RecallTaskModel(ndb.Model):
  """Model for each running/completed message recall task."""

  owner_email = ndb.StringProperty(required=True)
  message_criteria = ndb.StringProperty(required=True)
  domain = ndb.ComputedProperty(lambda self: self.owner_email.split('@')[1])
  start_datetime = ndb.DateTimeProperty(required=True, auto_now_add=True)
  end_datetime = ndb.DateTimeProperty(indexed=False, auto_now=True)
  task_state = ndb.StringProperty(required=True, default=TASK_STARTED,
                                  choices=TASK_STATES)
  is_aborted = ndb.BooleanProperty(required=True, default=True)

  @classmethod
  def FetchTaskFromSafeId(cls, user_domain, task_key_urlsafe):
    """Utility to query and fetch a specific task from its safe id.

    get() is a shortcut for fetch() of one record only.

    Args:
      user_domain: String to force safety check of proper domain.
      task_key_urlsafe: String representation of task key safe for urls.

    Returns:
      A single task model object.
    """
    return cls.GetQueryBySafeUrlTaskKey(user_domain, task_key_urlsafe).get()

  @classmethod
  def FetchOneUIPageOfTasksForDomain(cls, user_domain, urlsafe_cursor):
    """Utility to query and fetch all tasks.

    Args:
      user_domain: String to force safety check of proper domain.
      urlsafe_cursor: String cursor from previous fetch_page() calls.

    Returns:
      Iterable of one page of RecallTaskModel tasks.
    """
    return cls.GetQueryForAllTasks(user_domain).fetch_page(
        _TASK_ROWS_FETCH_PAGE, start_cursor=Cursor(urlsafe=urlsafe_cursor))

  @classmethod
  def GetTaskByKey(cls, task_key_id):
    """Helper to retrieve a task entity using its key.

    Args:
      task_key_id: String (serializable) unique id of the task record.

    Returns:
      The RecallTaskModel entity or None.
    """
    retries = 0
    task = None
    while not task and retries < _GET_ENTITY_RETRIES:
      task = cls.get_by_id(int(task_key_id))
      if task:
        return task
      time.sleep(2**retries)
      retries += 1
    raise recall_errors.MessageRecallDataError(
        'Cannot locate RecallTaskModel id=%s.', task_key_id)

  @classmethod
  def GetQueryBySafeUrlTaskKey(cls, user_domain, task_key_urlsafe):
    """Prepare a Query object to retrieve one specific task.

    Args:
      user_domain: String to force safety check of proper domain.
      task_key_urlsafe: String representation of task key safe for urls.

    Returns:
      Query object filtered to one specific task.
    """
    return cls.query(cls.domain == user_domain,
                     cls.key == ndb.Key(urlsafe=task_key_urlsafe))

  @classmethod
  def GetQueryForAllTasks(cls, user_domain):
    """Prepare a Query object to retrieve all tasks for a domain.

    Args:
      user_domain: String to force safety check of proper domain.

    Returns:
      Query object filtered to all tasks for a domain.
    """
    return cls.query(cls.domain == user_domain).order(-cls.start_datetime)

  @classmethod
  def SetTaskState(cls, task_key_id, new_state, is_aborted=True):
    """Utility method to update the state of the master task record.

    Args:
      task_key_id: String (serializable) unique id of the task record.
      new_state: String update for the ndb StringProperty field.
      is_aborted: Boolean; False when performing final update.
    """
    task = cls.GetTaskByKey(task_key_id)
    if task:
      if task.task_state != TASK_DONE:
        task.task_state = new_state
        if new_state == TASK_DONE:
          _LOG.warning('RecallTaskModel id=%s Done.', task_key_id)
      task.is_aborted = is_aborted
      task.put()

  def GetErrorReasonCountForTask(self):
    """Count the #error reasons associated with the current task.

    Returns:
      Integer number of error reasons associated with the current task.
    """
    return error_reason.ErrorReasonModel.GetErrorReasonCountForTask(
        task_key_id=self.key.id())

  def GetQueryForAllTaskUsers(self, user_state_filters=None,
                              message_state_filters=None):
    """Prepare a Query object to retrieve all users for a specific task.

    Args:
      user_state_filters: List of strings to filter users from the USER_STATES
                          list in domain_user.py.
                          e.g. ['Done', 'Suspended']
      message_state_filters: List of strings to filter users from the
                            MESSAGE_STATES list in domain_user.py.
                             e.g. ['Found', 'Purged']

    Returns:
      Query object filtered to all users in a specific task.
    """
    return domain_user.DomainUserToCheckModel.GetQueryForAllTaskUsers(
        task_key_id=self.key.id(),
        user_state_filters=user_state_filters,
        message_state_filters=message_state_filters)

  def GetUserCountForTask(self, user_state_filters=None,
                          message_state_filters=None):
    """Count the #users associated with the current task and message state.

    The states may be empty to count all users or the states may have
    elements to count users in a particular state.

    Args:
      user_state_filters: List of strings to filter users from the USER_STATES
                          list in domain_user.py.
                          e.g. ['Done', 'Suspended']
      message_state_filters: List of strings to filter users from the
                            MESSAGE_STATES list in domain_user.py.
                             e.g. ['Found', 'Purged']

    Returns:
      Integer number of users associated with the current task with the
      supplied message states.
    """
    return domain_user.DomainUserToCheckModel.GetUserCountForTask(
        task_key_id=self.key.id(),
        user_state_filters=user_state_filters,
        message_state_filters=message_state_filters)

  def GetUserCountForTaskWithTerminalUserStates(self):
    """Helper to count users who have completed processing.

    Returns:
      Integer number of users associated with the current task with
      terminal user states.
    """
    return (domain_user.DomainUserToCheckModel
            .GetUserCountForTaskWithTerminalUserStates(
                task_key_id=self.key.id()))

  def AmIAborted(self):
    return self.is_aborted and (self.task_state == TASK_DONE)

  @classmethod
  def IsTaskAborted(cls, task_key_id):
    """Convenience method to check if another task aborted the recall.

    Args:
      task_key_id: key id of the RecallTask model object for this recall.

    Returns:
      True if task found and aborted is True else False.
    """
    task = cls.GetTaskByKey(task_key_id=task_key_id)
    return task.is_aborted and (task.task_state == TASK_DONE)
