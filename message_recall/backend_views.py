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

"""Main view implementations that handle user requests.

The backend is organized in 4 phases with corresponding handlers:
  1. Phase1RecallMessagesHandler()
  2. Phase2RetrieveDomainUsersHandler()
  3. Phase3RecallUserMessagesHandler()
  4. Phase4WaitForTaskCompletionHandler()

Resource tuning discussion:
https://developers.google.com/appengine/articles/managing-resources
"""

import time

import log_utils
import mail_api
from models import domain_user
from models import error_reason
from models import recall_task
from models import sharded_counter
import recall_errors
import user_retriever
import view_utils
import webapp2

from google.appengine.api import apiproxy_stub_map
from google.appengine.api import runtime
from google.appengine.api.taskqueue import Error as TaskQueueError
from google.appengine.api.taskqueue import Queue
from google.appengine.api.taskqueue import Task
from google.appengine.ext import ndb


_LOG = log_utils.GetLogger('messagerecall.views')
_MONITOR_SLEEP_PERIOD_S = 10

# Write users to the db in batches to save time/rpcs.
_USER_PUT_MULTI_BATCH_SIZE = 100


def PartitionEmailPrefixes():
  """Divide the domain email namespace to allow concurrent tasks to search.

  The rules for gmail usernames are:
  a) Letters, numbers and . are allowed.
  b) The first character must be a letter or number.

  Returns:
    List of Strings which are the valid prefixes the user search tasks will
    use.
  """
  return list('abcdefghijklmnopqrstuvwxyz0123456789')


def GetEmailPartitionCount():
  """Helper to track partitioned tasks.

  Returns:
    Integer count of the number of (minimum) expected tasks.
  """
  return len(PartitionEmailPrefixes())


def MessageRecallShutdownHook():
  """Called by the runtime when shutting down instances."""
  apiproxy_stub_map.apiproxy.CancelApiCalls()
  raise recall_errors.MessageRecallShutdownError('Shutting down.')


class StartBackendHandler(webapp2.RequestHandler):
  """Handle '/_ah/start' requests to start a backend."""

  def get(self):  # pylint: disable=g-bad-name
    """Handler for /_ah/start get requests."""
    runtime.set_shutdown_hook(MessageRecallShutdownHook)
    self.response.status = 200


class BackendBaseHandler(webapp2.RequestHandler):
  """Setup common logging of timing for derived handlers."""

  def __init__(self, request, response):
    """RequestHandler initialization requires base class initialization."""
    self.initialize(request, response)
    self.init_time = time.time()

  def __del__(self):
    _LOG.debug('Handler for %s took %.2f seconds',
               self.request.url, time.time() - self.init_time)

  def handle_exception(self, exception, debug):  # pylint: disable=g-bad-name
    """Common exception handler for webapp2.

    Aborts could flood the log so the aborting code should log an entry as
    this handler will not log the many aborts it sees.

    Args:
      exception: Python Error(Exception) object.
      debug: Boolean; True if the wsgi application has debug enabled.
    """
    if not isinstance(exception, recall_errors.MessageRecallAbortedError):
      _LOG.exception(exception)
      _LOG.debug('Is the web application in debug mode? %s.', debug)
      sharded_counter.IncrementCounterAndGetCount(
          name=view_utils.MakeBackendErrorCounterName(self._task_key_id))
      _LOG.debug('Status=%s.', self.response.status)
      self.response.status = 500

  def post(self):  # pylint: disable=g-bad-name
    """Base class post handler with common operations."""
    self._task_key_id = int(self.request.get('task_key_id'))
    if recall_task.RecallTaskModel.IsTaskAborted(self._task_key_id):
      raise recall_errors.MessageRecallAbortedError()


class Phase1RecallMessagesHandler(BackendBaseHandler):
  """Handle '/backend/recall_messages - the master task for recalling messages.

  This task, invoked in response to a task enqueued by the frontend, kicks off
  tasks to retrieve users which then kick off tasks to actually recall
  messages using the users retrieved.

  Adds tasks to an AppEngine push queue to retrieve users then adds tasks to
  recall messages using the users returned.
  """

  def _AddUserRetrievalTask(self, task):
    """Helper to transactionally add the tasks.

    Do not set transactional=True in the Task because Push Queues have a
    5 Task per add limit when transactional=True per:
    http://developers.google.com/appengine/docs/python/taskqueue/overview-push

    Args:
      task: Task or list of Tasks to retrieve domain users.

    Raises:
      re-raises any taskqueue errors raised.
    """
    try:
      Queue('retrieve-users-queue').add(task=task)
    except TaskQueueError:
      view_utils.FailRecallTask(
          task_key_id=self._task_key_id,
          reason_string='Failed to enqueue retrieve users tasks.')
      raise

  def _EnqueueUserRetrievalTasks(self, message_criteria, owner_email):
    """Efficiently add tasks to enumerate domain users as a list (bulk add).

    Bulk add() saves roundtrips (rpc calls).

    Args:
      message_criteria: String criteria (message-id) to recall.
      owner_email: String email address of user running this recall.
    """
    user_retrieval_tasks = []
    # Use countdown to space out these requests a little.
    # There is a 15 request/s quota on the Admin SDK API.
    limit_requests_s = 15
    for prefix_counter, email_prefix in enumerate(PartitionEmailPrefixes()):
      user_retrieval_tasks.append(
          Task(countdown=(prefix_counter / limit_requests_s),
               name='%s_%s_%s' % (
                   view_utils.CreateSafeUserEmailForTaskName(owner_email),
                   email_prefix,
                   view_utils.GetCurrentDateTimeForTaskName()),
               params={'email_prefix': email_prefix,
                       'message_criteria': message_criteria,
                       'owner_email': owner_email,
                       'task_key_id': self._task_key_id},
               target='recall-backend',
               url='/backend/retrieve_domain_users'))
    self._AddUserRetrievalTask(task=user_retrieval_tasks)

  def post(self):  # pylint: disable=g-bad-name
    """Handler for /backend/recall_messages post requests.

    These tasks handled by Phase2RetrieveDomainUsersHandler().
    """
    super(Phase1RecallMessagesHandler, self).post()
    recall_task.RecallTaskModel.SetTaskState(
        task_key_id=self._task_key_id,
        new_state=recall_task.TASK_GETTING_USERS)
    self._EnqueueUserRetrievalTasks(
        message_criteria=self.request.get('message_criteria'),
        owner_email=self.request.get('owner_email'))


class Phase2RetrieveDomainUsersHandler(BackendBaseHandler):
  """Handle '/backend/retrieve_domain_users to gather domain users."""

  def handle_exception(self, exception, debug):  # pylint: disable=g-bad-name
    """Specialize common exception handler for counter decrementing.

    Args:
      exception: Python Error(Exception) object.
      debug: Boolean; True if the wsgi application has debug enabled.
    """
    super(Phase2RetrieveDomainUsersHandler, self).handle_exception(
        exception, debug)
    if self._was_incremented:
      self._DecrementRetrievalStartedTasksCount()

  def _AddUserRecordsToDB(self, users_to_add):
    """Helper to perform ndb put() with error handling.

    Args:
      users_to_add: List of user (DomainUserToCheckModel) entities to add.
    """
    ndb.put_multi(users_to_add)

  def _AddUserRecordsPage(self, user_tuples):
    """Helper to add a user record to the data model for this recall task.

    User retrieval is optimized for minimum rpc's.  Users are retrieved using
    the API by the largest possible page size (500 users).  But, users are
    efficiently added to NDB in batches of 100.

    Args:
      user_tuples: List of tuples (1 for each user) with a String email
                   address and the suspended status of the users to check.
    """
    current_user_index = 0
    user_count = len(user_tuples)
    users_to_add = []
    for user_email, is_suspended in user_tuples:
      if recall_task.RecallTaskModel.IsTaskAborted(self._task_key_id):
        return
      if domain_user.DomainUserToCheckModel.IsUserEmailEntityInTask(
          self._task_key_id, user_email):
        user_count -= 1
        continue
      user_to_add = domain_user.DomainUserToCheckModel(
          recall_task_id=self._task_key_id, user_email=user_email)
      if is_suspended:
        user_to_add.message_state = domain_user.MESSAGE_UNKNOWN
        user_to_add.user_state = domain_user.USER_SUSPENDED
      users_to_add.append(user_to_add)
      if (len(users_to_add) == _USER_PUT_MULTI_BATCH_SIZE or
          (current_user_index == (user_count - 1) and users_to_add)):
        self._AddUserRecordsToDB(users_to_add)
        users_to_add = []
      current_user_index += 1
    if users_to_add:
      view_utils.FailRecallTask(
          task_key_id=self._task_key_id,
          reason_string='Unexpectedly found %s users not stored.' %
          len(users_to_add),
          raise_exception=True)

  def _AddUserRecallTasks(self, user_recall_tasks):
    """Helper to enqueue list of user recall tasks in batches.

    Args:
      user_recall_tasks: Task or list of Tasks; one for each user.

    Raises:
      re-raises any errors with task queue.
    """
    Queue('user-recall-queue').add(task=user_recall_tasks)

  def _AddTaskToMonitorUserRecallTasksHaveCompleted(self, owner_email):
    """Adds final task which monitors user recall tasks for completion.

    Args:
      owner_email: String email address of user running this recall.
    """
    self._AddUserRecallTasks(user_recall_tasks=Task(
        name='%s_monitor_%s' % (
            view_utils.CreateSafeUserEmailForTaskName(owner_email),
            view_utils.GetCurrentDateTimeForTaskName()),
        params={'task_key_id': self._task_key_id},
        target='recall-backend',
        url='/backend/wait_for_task_completion'))

  def _AreUserRetrievalTasksCompleted(self):
    """Helper to increment a counter and check if expected count is reached.

    If the expected #tasks matches the current count of completed tasks we are
    done.

    Returns:
      Boolean; True if completed all the tasks allotted.
    """
    retrieval_ended_count = self._IncrementRetrievalEndedTasksCount()
    retrieval_started_count = sharded_counter.GetCounterCount(
        name=view_utils.MakeRetrievalStartedCounterName(self._task_key_id))
    task = recall_task.RecallTaskModel.GetTaskByKey(self._task_key_id)
    return ((task.task_state == recall_task.TASK_GETTING_USERS) and
            (retrieval_started_count >= GetEmailPartitionCount()) and
            (retrieval_ended_count >= GetEmailPartitionCount()))

  def _EnqueueUserRecallTasks(self, message_criteria, owner_email):
    """Efficiently add tasks for each user to recall messages (bulk add).

    Bulk add() saves roundtrips (rpc calls).

    Args:
      message_criteria: String criteria (message-id) to recall.
      owner_email: String email address of user running this recall.
    """
    if recall_task.RecallTaskModel.IsTaskAborted(self._task_key_id):
      return
    cursor = None
    while True:
      user_recall_tasks = []
      results, cursor, unused_more = (
          domain_user.DomainUserToCheckModel.FetchOnePageOfActiveUsersForTask(
              task_key_id=self._task_key_id,
              cursor=cursor))
      for user in results:
        user_recall_tasks.append(Task(
            name='%s_%s_%s' % (
                view_utils.CreateSafeUserEmailForTaskName(owner_email),
                view_utils.CreateSafeUserEmailForTaskName(user.user_email),
                view_utils.GetCurrentDateTimeForTaskName()),
            params={'message_criteria': message_criteria,
                    'task_key_id': self._task_key_id,
                    'user_email': user.user_email,
                    'user_key_id': user.key.id()},
            target='recall-backend',
            url='/backend/recall_user_messages'))
      if not user_recall_tasks:
        break
      self._AddUserRecallTasks(user_recall_tasks=user_recall_tasks)

  def _IncrementRetrievalStartedTasksCount(self):
    """Increment sharded counter when each user-retrieval-task starts.

    Returns:
      Final value of the counter after the increment of 1.
    """
    retrieval_started_count = sharded_counter.IncrementCounterAndGetCount(
        name=view_utils.MakeRetrievalStartedCounterName(self._task_key_id))
    if not retrieval_started_count:
      view_utils.FailRecallTask(
          task_key_id=self._task_key_id,
          reason_string='Unexpected retrieval_started count: %s.' %
          retrieval_started_count,
          raise_exception=True)
    self._was_incremented = True
    return retrieval_started_count

  def _DecrementRetrievalStartedTasksCount(self):
    """Decrement sharded counter when each user-retrieval-task aborts."""
    sharded_counter.IncrementCounterAndGetCount(
        name=view_utils.MakeRetrievalStartedCounterName(self._task_key_id),
        delta=-1)

  def _IncrementRetrievalEndedTasksCount(self):
    """Increment sharded counter when each user-retrieval-task ends.

    Returns:
      Final value of the counter after the increment of 1.
    """
    retrieval_ended_count = sharded_counter.IncrementCounterAndGetCount(
        name=view_utils.MakeRetrievalEndedCounterName(self._task_key_id))
    if not retrieval_ended_count:
      view_utils.FailRecallTask(
          task_key_id=self._task_key_id,
          reason_string='Unexpected retrieval_ended count: %s.' %
          retrieval_ended_count,
          raise_exception=True)
    return retrieval_ended_count

  def _RetrieveAndAddUsers(self, email_prefix, owner_email):
    """Search domain users and add returned users to the data store.

    Each tasks searches a domain user subset based on the email_prefix.

    Args:
      email_prefix: String with the first n characters of an email address.
      owner_email: String email address of the user who owns the task.
                   The search will occur in this users domain.
    """
    try:
      for user_tuples_page in user_retriever.DomainUserRetriever(
          owner_email=owner_email,
          user_domain=view_utils.GetUserDomain(owner_email),
          email_query_prefix=email_prefix,
          use_glob=True).RetrieveDomainUsers():
        self._AddUserRecordsPage(user_tuples=user_tuples_page)
    except recall_errors.MessageRecallError:
      view_utils.FailRecallTask(
          task_key_id=self._task_key_id,
          reason_string='Failure retrieving users.')
      raise

  def post(self):  # pylint: disable=g-bad-name
    """Handler for /backend/retrieve_domain_users post requests.

    Generates tasks handled by Phase3RecallUserMessagesHandler().
    """
    super(Phase2RetrieveDomainUsersHandler, self).post()
    self._was_incremented = False
    self._IncrementRetrievalStartedTasksCount()
    owner_email = self.request.get('owner_email')
    self._RetrieveAndAddUsers(email_prefix=self.request.get('email_prefix'),
                              owner_email=owner_email)
    if self._AreUserRetrievalTasksCompleted():
      recall_task.RecallTaskModel.SetTaskState(
          task_key_id=self._task_key_id,
          new_state=recall_task.TASK_RECALLING)
      self._EnqueueUserRecallTasks(
          message_criteria=self.request.get('message_criteria'),
          owner_email=owner_email)
      self._AddTaskToMonitorUserRecallTasksHaveCompleted(owner_email)


class Phase3RecallUserMessagesHandler(BackendBaseHandler):
  """Handle '/backend/recall_user_messages - check/recall messages for one user.

  Interfaces with gmail via imap for an individual user.
  """

  def _RecallUserMessages(self, message_criteria, user_email, user_key_id):
    """Helper to recall messages and set user state.

    Mail errors are noted in the user state and log and not re-raised.

    Args:
      message_criteria: String criteria (message-id) to recall.
      user_email: String email address of the user to check.
      user_key_id: Int unique id of the user entity to update state.
    """
    try:
      with mail_api.GmailHelper(self._task_key_id, user_key_id, user_email,
                                message_criteria) as gmail_helper:
        if gmail_helper.CheckIfMessageExists():
          gmail_helper.DeleteMessage()
    except recall_errors.MessageRecallGmailError as e:
      error_reason.ErrorReasonModel.AddTaskErrorReason(
          task_key_id=self._task_key_id,
          error_reason=str(e),
          user_email=user_email)

  def post(self):  # pylint: disable=g-bad-name
    """Handler for /backend/recall_user_messages post requests."""
    super(Phase3RecallUserMessagesHandler, self).post()
    self._RecallUserMessages(
        message_criteria=self.request.get('message_criteria'),
        user_email=self.request.get('user_email'),
        user_key_id=int(self.request.get('user_key_id')))


class Phase4WaitForTaskCompletionHandler(BackendBaseHandler):
  """Handle '/backend/wait_for_task_completion - Wait for all tasks complete."""

  def _AreAllUserRecallTasksCompleted(self):
    """Helper to check if all user entities are completed.

    Returns:
      Boolean; True if all user entities are completed (in a terminal state).
    """
    task = recall_task.RecallTaskModel.GetTaskByKey(self._task_key_id)
    return (task.GetUserCountForTask() ==
            task.GetUserCountForTaskWithTerminalUserStates())

  def post(self):  # pylint: disable=g-bad-name
    """Handler for /backend/recall_user_messages post requests."""
    super(Phase4WaitForTaskCompletionHandler, self).post()
    while not self._AreAllUserRecallTasksCompleted():
      time.sleep(_MONITOR_SLEEP_PERIOD_S)
    recall_task.RecallTaskModel.SetTaskState(task_key_id=self._task_key_id,
                                             new_state=recall_task.TASK_DONE,
                                             is_aborted=False)
