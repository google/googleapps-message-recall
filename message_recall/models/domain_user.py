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

"""Database models for candidate domain users to check for message presence."""

import log_utils

from google.appengine.datastore.datastore_query import Cursor
from google.appengine.ext import ndb


_LOG = log_utils.GetLogger('messagerecall.models.domain_user')
_USER_ROWS_FETCH_PAGE = 10

USER_STARTED = 'Started'
USER_RECALLING = 'Recalling'
USER_CONNECT_FAILED = 'Imap Connect Failed'
USER_IMAP_DISABLED = 'Imap Disabled'
USER_DONE = 'Done'
USER_ABORTED = 'Aborted'
USER_SUSPENDED = 'Suspended'

USER_STATES = [USER_STARTED, USER_RECALLING, USER_CONNECT_FAILED,
               USER_IMAP_DISABLED, USER_DONE, USER_ABORTED, USER_SUSPENDED]
ACTIVE_USER_STATES = [USER_STARTED, USER_RECALLING, USER_CONNECT_FAILED,
                      USER_IMAP_DISABLED, USER_ABORTED]
TERMINAL_USER_STATES = [USER_CONNECT_FAILED, USER_IMAP_DISABLED,
                        USER_DONE, USER_ABORTED, USER_SUSPENDED]

MESSAGE_UNKNOWN = 'Unknown'
MESSAGE_FOUND = 'Found'
MESSAGE_NOT_FOUND = 'Not Found'
MESSAGE_PURGED = 'Purged'
MESSAGE_VERIFIED_PURGED = 'Verified Purged'
MESSAGE_DELETE_FAILED = 'Delete Failed'
MESSAGE_VERIFY_FAILED = 'Verify Failed'

MESSAGE_STATES = [MESSAGE_UNKNOWN, MESSAGE_FOUND, MESSAGE_NOT_FOUND,
                  MESSAGE_PURGED, MESSAGE_VERIFIED_PURGED,
                  MESSAGE_DELETE_FAILED, MESSAGE_VERIFY_FAILED]


class DomainUserToCheckModel(ndb.Model):
  """Model to track work against individual users in recalling messages.

  Recall-task-users are domain users that will be considered as possible
  message recipients. These records track progress checking each user and
  will be used for post-recall status reporting.
  """

  recall_task_id = ndb.IntegerProperty(required=True)
  user_email = ndb.StringProperty(required=True)
  start_datetime = ndb.DateTimeProperty(required=True, auto_now_add=True,
                                        indexed=False)
  end_datetime = ndb.DateTimeProperty(indexed=False, auto_now=True)
  user_state = ndb.StringProperty(required=True, default=USER_STARTED,
                                  choices=USER_STATES)
  message_state = ndb.StringProperty(required=True, default=MESSAGE_UNKNOWN,
                                     choices=MESSAGE_STATES)
  is_aborted = ndb.BooleanProperty(required=True, default=True)

  @classmethod
  def _GetUserByKey(cls, user_key_id):
    """Helper to retrieve a user entity.

    User entities are not direct descendants of their corresponding recall
    task entities. This allows us to scale very frequent state updates of
    user entities across thousands+ in-flight users.

    Args:
      user_key_id: String (serializable) unique id of the user.

    Returns:
      The ndb DomainUserToCheckModel entity or None.
    """
    user = cls.get_by_id(id=user_key_id)
    if not user:
      _LOG.debug('Cannot locate DomainUserToCheckModel id=%s.', user_key_id)
    return user

  @classmethod
  def FetchOnePageOfActiveUsersForTask(cls, task_key_id, cursor):
    """Utility to query and fetch all active users.

    Used to retrieve the entire list of (not suspended) domain users to process.

    Args:
      task_key_id: Int unique id of the task record.
      cursor: Cursor from previous fetch_page() calls.

    Returns:
      Iterable of one page of DomainUserToCheckModel users.
    """
    return cls.GetQueryForAllTaskUsers(
        task_key_id=task_key_id,
        user_state_filters=ACTIVE_USER_STATES).fetch_page(
            _USER_ROWS_FETCH_PAGE, start_cursor=cursor)

  @classmethod
  def FetchOneUIPageOfUsersForTask(cls, task_key_urlsafe, urlsafe_cursor,
                                   user_state_filters=None,
                                   message_state_filters=None):
    """Utility to query and fetch all users for UI pages.

    Args:
      task_key_urlsafe: String unique id of the task record.
      urlsafe_cursor: String cursor from previous fetch_page() calls.
                      This is a publishable version acquired via '.urlsafe()'.
      user_state_filters: List of strings to filter users.
      message_state_filters: List of strings to filter users.

    Returns:
      Iterable of one page of DomainUserToCheckModel users.
    """
    return cls.GetQueryForAllTaskUsers(
        task_key_id=ndb.Key(urlsafe=task_key_urlsafe).id(),
        user_state_filters=user_state_filters,
        message_state_filters=message_state_filters).fetch_page(
            _USER_ROWS_FETCH_PAGE,
            start_cursor=Cursor(urlsafe=urlsafe_cursor))

  @classmethod
  def GetQueryForAllTaskUsers(cls, task_key_id, user_state_filters=None,
                              message_state_filters=None):
    """Prepare a Query object to retrieve all users of a task.

    The filters imply an OR operator when multiple user_states or message_states
    are supplied.  However the results of the user_states filter are ANDed with
    the results of the message_states filter.  When filters are included, the
    order must be on key.

    Args:
      task_key_id: Int unique id of the task record.
      user_state_filters: List of strings to filter users.
      message_state_filters: List of strings to filter users.

    Returns:
      Query object filtered to all users for one task.
    """
    query = cls.query(cls.recall_task_id == task_key_id)
    if user_state_filters or message_state_filters:
      query = query.order(cls._key)
    else:
      query = query.order(cls.user_email)
    if user_state_filters:
      query = query.filter(cls.user_state.IN(user_state_filters))
    if message_state_filters:
      query = query.filter(cls.message_state.IN(message_state_filters))
    return query

  @classmethod
  def GetUserCountForTask(cls, task_key_id, user_state_filters=None,
                          message_state_filters=None):
    """Count the #users associated with a task [with user/message states].

    Args:
      task_key_id: Int unique id of the task record.
      user_state_filters: List of strings to filter users.
      message_state_filters: List of strings to filter users.

    Returns:
      Integer number of users associated with the current task with the
      supplied message states.
    """
    return cls.GetQueryForAllTaskUsers(
        task_key_id=task_key_id,
        user_state_filters=user_state_filters,
        message_state_filters=message_state_filters).count(keys_only=True)

  @classmethod
  def IsUserEmailEntityInTask(cls, task_key_id, user_email):
    """Checks if a user entity already exists in this task.

    Args:
      task_key_id: Int unique id of the task record.
      user_email: String email address of a user to find.

    Returns:
      Bool; True if the user already exists else False.
    """
    return cls.query(cls.recall_task_id == task_key_id,
                     cls.user_email == user_email).count(keys_only=True) > 0

  @classmethod
  def GetUserCountForTaskWithTerminalUserStates(cls, task_key_id):
    """Count the #users associated with a task with terminal user states.

    Args:
      task_key_id: Int unique id of the task record.

    Returns:
      Integer number of users associated with the current task with
      terminal user states.
    """
    return cls.GetQueryForAllTaskUsers(
        task_key_id=task_key_id,
        user_state_filters=TERMINAL_USER_STATES).count(keys_only=True)

  @classmethod
  def SetMessageState(cls, user_key_id, new_state):
    """Describe progress finding/purging a message for one user.

    Args:
      user_key_id: String (serializable) unique id of the user.
      new_state: String update for the ndb StringProperty field.
    """
    user = cls._GetUserByKey(user_key_id)
    if user:
      user.message_state = new_state
      user.put()

  @classmethod
  def SetUserState(cls, user_key_id, new_state):
    """Utility method to update the state of the user record.

    Args:
      user_key_id: String (serializable) unique id of the user.
      new_state: String update for the ndb StringProperty field.
    """
    user = cls._GetUserByKey(user_key_id)
    if user:
      if user.user_state not in TERMINAL_USER_STATES:
        user.user_state = new_state
      user.put()
