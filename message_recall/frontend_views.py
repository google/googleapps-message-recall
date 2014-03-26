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

"""Frontend view implementations that handle user requests."""

import os
import re
import socket
import time

import jinja2
import log_utils
from models import domain_user
from models import error_reason
from models import recall_task
from models import sharded_counter
import recall_errors
import user_retriever
import view_utils
import webapp2
import wtforms
from wtforms import validators
import xsrf_helper

from google.appengine.api import memcache
from google.appengine.api import users
from google.appengine.api.taskqueue import Error as TaskQueueError
from google.appengine.api.taskqueue import Task
from google.appengine.runtime import apiproxy_errors


_APPLICATION_DIR = os.path.dirname(__file__)
_CREATE_TASK_ACTION = 'CreateTask#ns'
_GET_USER_MAX_RETRIES = 2
_LOG = log_utils.GetLogger('messagerecall.views')
_MESSAGE_ID_REGEX = re.compile(r'^[\w+-=.]+@[\w.]+$')
_MESSAGE_ID_MAX_LEN = 100
_USER_ADMIN_CACHE_NAMESPACE = 'messagerecall_useradmin#ns'
_USER_ADMIN_CACHE_TIMEOUT_S = 60 * 60 * 2  # 2 hours
_USER_BILLING_CACHE_TIMEOUT_S = 60 * 60 * 24  # 24 hours
_APPLICATION_BILLING_CACHE_NAMESPACE = 'messagerecall_billing#ns'


def _CacheUserEmailBillingEnabled(user_email):
  """Cache the user_email to avoid billing-check rountrips.

  Wrapped in a separate method to aid error handling.

  Args:
    user_email: String email address of the form user@domain.com.

  Raises:
    MessageRecallMemcacheError: If the add fails so cache issues can be noticed.
  """
  if not memcache.add(user_email, True, time=_USER_BILLING_CACHE_TIMEOUT_S,
                      namespace=_APPLICATION_BILLING_CACHE_NAMESPACE):
    raise recall_errors.MessageRecallMemcacheError(
        'Unexpectedly unable to add application billing information to '
        'memcache. Please try again.')


def _CacheUserEmailAsAdmin(user_email):
  """Cache the admin user_email to avoid rountrips.

  Wrapped in a separate method to aid error handling.

  Args:
    user_email: String email address of the form user@domain.com.

  Raises:
    MessageRecallMemcacheError: If the add fails so cache issues can be noticed.
  """
  if not memcache.add(user_email, True, time=_USER_ADMIN_CACHE_TIMEOUT_S,
                      namespace=_USER_ADMIN_CACHE_NAMESPACE):
    raise recall_errors.MessageRecallMemcacheError(
        'Unexpectedly unable to add admin user information to memcache. '
        'Please try again.')


def _SafelyGetCurrentUserEmail():
  """Retrieve the current user's email or raise an exception.

  We set 'login: required' in app.yaml so all users should be logged-in.
  But, is has been observed that users.get_current_user() *can* return None.
  Therefore, this must be checked.

  Returns:
    String email address of the currently logged-in user.

  Raises:
    MessageRecallAuthenticationError: If current user is noticed as None.
  """
  user = None
  get_user_attempts = 0
  while not user and get_user_attempts < _GET_USER_MAX_RETRIES:
    user = users.get_current_user()
    get_user_attempts += 1
  if not user:
    raise recall_errors.MessageRecallAuthenticationError(
        'A logged-in user was not retrieved. Please try again.')
  return user.email()


def _FailIfBillingNotEnabled(user_email):
  """Ensure Google Apps Domain has billing enabled.

  Billing-enabled is required to use sockets in AppEngine.
  The IMAP mail api uses sockets.  So this application requires billing
  to be enabled.

  If billing not enabled, this is observed:

  FeatureNotEnabledError: The Socket API will be enabled for this application
                          once billing has been enabled in the admin console.

  Args:
    user_email: String email address of the form user@domain.com.

  Raises:
    MessageRecallAuthenticationError: If user is not properly authorized.
  """
  if memcache.get(user_email, namespace=_APPLICATION_BILLING_CACHE_NAMESPACE):
    return
  imap_host = 'imap.gmail.com'
  imap_port = 993
  # The socket is discarded after 2min of no use.
  s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  try:
    s.bind((imap_host, imap_port))
  except apiproxy_errors.FeatureNotEnabledError as e:
    raise recall_errors.MessageRecallError(
        'This AppEngine application requires billing status: '
        '"Billing Enabled".  Please choose "Enable Billing" in the AppEngine '
        'admin console for this application (%s).' % e)
  except Exception as e:
    # Expect "[Errno 13] Permission denied" once billing enabled.
    if str(e) != '[Errno 13] Permission denied':
      raise
  _CacheUserEmailBillingEnabled(user_email)


def _FailIfNonAdminUser(user_email):
  """Ensure user possesses adequate Admin authority.

  This AppEngine application should set Authentication Type to:
  'Google Accounts API'.

  Per documentation, isAdmin is True if the user is a member of the
  Google Apps System: Role = Super Admin.
  https://developers.google.com/admin-sdk/directory/v1/reference/

  If the user is found to be a properly authorized admin-user of this
  application, then cache that fact to avoid roundtrips to the Admin SDK
  for a little while.

  Args:
    user_email: String email address of the form user@domain.com.

  Raises:
    MessageRecallAuthenticationError: If user is not properly authorized.
  """
  if memcache.get(user_email, namespace=_USER_ADMIN_CACHE_NAMESPACE):
    return
  retriever = user_retriever.DomainUserRetriever(
      owner_email=user_email,
      user_domain=view_utils.GetUserDomain(user_email),
      search_query='email:%s' % user_email)
  if not retriever.GetUserAttribute(user_email, 'isAdmin'):
    # User is not a super-admin...
    raise recall_errors.MessageRecallAuthenticationError(
        'User %s is not authorized for Message Recall in this domain.'
        % user_email)
  _CacheUserEmailAsAdmin(user_email)


def _PreventUnauthorizedAccess():
  """Ensure user possesses adequate Admin authority."""
  current_user_email = _SafelyGetCurrentUserEmail()
  _FailIfNonAdminUser(current_user_email)
  _FailIfBillingNotEnabled(current_user_email)


class UIBasePageHandler(webapp2.RequestHandler):
  """Setup common template handling for derived handlers."""

  def __init__(self, request, response):
    """RequestHandler initialization requires base class initialization."""
    self.initialize(request, response)

    self.init_time = time.time()
    template_dir = os.path.join(_APPLICATION_DIR, 'templates')
    self._jinja_env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(template_dir),
        extensions=['jinja2.ext.autoescape'],
        autoescape=True)

  def __del__(self):
    _LOG.debug('Handler for %s took %.2f seconds',
               self.request.url, time.time() - self.init_time)

  def handle_exception(self, exception, debug):  # pylint: disable=g-bad-name
    """Common exception handler for webapp2."""
    _LOG.exception(exception)
    _LOG.debug('Is the web application in debug mode? %s.', debug)
    self._WriteTemplate(
        template_file='error',
        tpl_exception=exception,
        tpl_unauthorized=isinstance(
            exception, recall_errors.MessageRecallAuthenticationError))

  def _WriteTemplate(self, template_file, **kwargs):
    """Common method to write from a template.

    Args:
      template_file: String name of a file that exists within the template
                     folder.  For subdirectories the name may be 'sub/file'.
      **kwargs: A dictionary of key-value pairs that will be available
                within the template.
    """
    kwargs['tpl_logout_url'] = users.create_logout_url('/')
    kwargs['tpl_user_name'] = _SafelyGetCurrentUserEmail()
    if '.' not in template_file:
      template_file = '%s.html' % template_file
    self.response.headers['X-Frame-Options'] = 'DENY'  # Prevent clickjacking.
    self.response.write(
        self._jinja_env.get_template(template_file).render(kwargs))


class AboutPageHandler(UIBasePageHandler):
  """Handle '/about' requests to show app about info."""

  def get(self):  # pylint: disable=g-bad-name
    """Handler for /about get requests."""
    _PreventUnauthorizedAccess()
    self._WriteTemplate('about')


class CreateTaskForm(wtforms.Form):
  """Wrap and validate the form that ingests user input for a recall task.

  Uses Regexp for xss protection to ensure no html tag characters are allowed.
  """
  message_criteria = wtforms.TextField(
      label='Message-ID', default='', validators=[
          validators.Length(min=1, max=_MESSAGE_ID_MAX_LEN,
                            message=(u'message-id must be 1-%s characters.' %
                                     _MESSAGE_ID_MAX_LEN)),
          validators.Regexp(_MESSAGE_ID_REGEX,
                            message=(u'message-id format is: local-part@domain.'
                                     'com (no spaces allowed).'))])

  @property
  def sanitized_message_criteria(self):
    """Helper to ensure message-id field has no extra junk.

    Returns:
      String as a safely scrubbed searchable message-id.
    """
    return self.message_criteria.data.strip()


class CreateTaskPageHandler(UIBasePageHandler, xsrf_helper.XsrfHelper):
  """Handle '/create_task' to show default page."""

  def get(self):  # pylint: disable=g-bad-name
    """Handler for /create_task get requests."""
    _PreventUnauthorizedAccess()
    self._WriteTemplate(
        template_file='create_task',
        tpl_create_task_form=CreateTaskForm(self.request.GET),
        xsrf_token=self.GetXsrfToken(user_email=_SafelyGetCurrentUserEmail(),
                                     action_id=_CREATE_TASK_ACTION))

  def _EnqueueMasterRecallTask(self, owner_email, message_criteria,
                               task_key_id):
    """Add master recall task with error handling.

    Args:
      owner_email: String email address of user running this recall.
      message_criteria: String criteria (message-id) to recall.
      task_key_id: Int unique id of the parent task.

    Raises:
      re-raises any task queue errors.
    """
    task_name = '%s_%s' % (
        view_utils.CreateSafeUserEmailForTaskName(owner_email),
        view_utils.GetCurrentDateTimeForTaskName())
    master_task = Task(name=task_name,
                       params={'owner_email': owner_email,
                               'task_key_id': task_key_id,
                               'message_criteria': message_criteria},
                       target='0.recall-backend',
                       url='/backend/recall_messages')
    try:
      master_task.add(queue_name='recall-messages-queue')
    except TaskQueueError:
      view_utils.FailRecallTask(task_key_id=task_key_id,
                                reason_string='Failed to enqueue master task.')
      raise

  def _CreateNewTask(self, owner_email, message_criteria):
    """Helper to create new task db entity and related Task for the backend.

    If the master task fails creation in the db, the error will be raised
    for the user to view.

    If the master task fails to be enqueued, the task state is updated to
    ABORTED.

    Args:
      owner_email: String email address of the user. Used in authorization.
      message_criteria: String criteria used to find message(s) to recall.

    Returns:
      Urlsafe (String) key for the RecallTaskModel entity that was created.
    """
    recall_task_entity = recall_task.RecallTaskModel(
        owner_email=owner_email,
        message_criteria=message_criteria)
    recall_task_key = recall_task_entity.put()
    self._EnqueueMasterRecallTask(owner_email=owner_email,
                                  message_criteria=message_criteria,
                                  task_key_id=recall_task_key.id())
    return recall_task_key.urlsafe()

  def post(self):  # pylint: disable=g-bad-name
    """Handler for /create_task post requests."""
    _PreventUnauthorizedAccess()
    current_user_email = _SafelyGetCurrentUserEmail()
    create_task_form = CreateTaskForm(self.request.POST)

    if not self.IsXsrfTokenValid(
        user_email=current_user_email,
        action_id=_CREATE_TASK_ACTION,
        submitted_xsrf_token=self.request.get('xsrf_token')):
      raise recall_errors.MessageRecallXSRFError(
          '[%s] Cross Site Request Forgery Checks Failed!' % current_user_email)
    if not create_task_form.validate():
      self._WriteTemplate(
          template_file='create_task',
          tpl_create_task_form=create_task_form,
          xsrf_token=self.GetXsrfToken(user_email=current_user_email,
                                       action_id=_CREATE_TASK_ACTION))
      return
    self.redirect('/task/%s' % self._CreateNewTask(
        owner_email=current_user_email,
        message_criteria=create_task_form.sanitized_message_criteria))


class DebugTaskPageHandler(UIBasePageHandler):
  """Handle '/task/debug' requests to show app debug info."""

  def get(self, task_key_urlsafe):  # pylint: disable=g-bad-name
    """Handler for /task/debug get requests.

    Args:
      task_key_urlsafe: String representation of task key safe for urls.
    """
    _PreventUnauthorizedAccess()
    task = recall_task.RecallTaskModel.FetchTaskFromSafeId(
        user_domain=view_utils.GetUserDomain(_SafelyGetCurrentUserEmail()),
        task_key_urlsafe=task_key_urlsafe)
    task_key_id = task.key.id() if task else 0
    counter_tuples = [
        ('User Retrieval Tasks Started (Expected)',
         sharded_counter.GetCounterCount(
             view_utils.MakeRetrievalStartedCounterName(task_key_id))),
        ('User Retrieval Tasks Ended (Actual)',
         sharded_counter.GetCounterCount(
             view_utils.MakeRetrievalEndedCounterName(task_key_id))),
        ('Task Backend Errors (Automatically Retried)',
         sharded_counter.GetCounterCount(
             view_utils.MakeBackendErrorCounterName(task_key_id)))]
    self._WriteTemplate(template_file='debug_task',
                        tpl_counter_tuples=counter_tuples, tpl_task=task)


class HistoryPageHandler(UIBasePageHandler):
  """Handle '/history' to show default page."""

  def get(self):  # pylint: disable=g-bad-name
    """Handler for /history get requests."""
    _PreventUnauthorizedAccess()
    previous_cursor = self.request.get('task_cursor')
    results, cursor, more = (
        recall_task.RecallTaskModel.FetchOneUIPageOfTasksForDomain(
            user_domain=view_utils.GetUserDomain(_SafelyGetCurrentUserEmail()),
            urlsafe_cursor=previous_cursor))
    self._WriteTemplate(template_file='history', tpl_tasks=results,
                        tpl_previous_cursor=previous_cursor, tpl_cursor=cursor,
                        tpl_more=more)


class LandingPageHandler(UIBasePageHandler):
  """Handle '/' to show default page."""

  def get(self):  # pylint: disable=g-bad-name
    """Handler for / get requests."""
    _PreventUnauthorizedAccess()
    self._WriteTemplate('landing')


class TaskDetailsPageHandler(UIBasePageHandler):
  """Handle '/task' requests to show task details.

  This page will show model fields such as task_state and calculated items
  such as 'elapsed time' for a single task.
  """

  def get(self, task_key_urlsafe):  # pylint: disable=g-bad-name
    """Handler for /task get requests.

    Args:
      task_key_urlsafe: String representation of task key safe for urls.
    """
    _PreventUnauthorizedAccess()
    self._WriteTemplate(
        template_file='task',
        tpl_task=recall_task.RecallTaskModel.FetchTaskFromSafeId(
            user_domain=view_utils.GetUserDomain(_SafelyGetCurrentUserEmail()),
            task_key_urlsafe=task_key_urlsafe))


class TaskProblemsPageHandler(UIBasePageHandler):
  """Handle '/task/problems' requests to show user details.

  This page will show a list of errors encountered during a recall.
  """

  def get(self, task_key_urlsafe):  # pylint: disable=g-bad-name
    """Handler for /task/errors get requests.

    Args:
      task_key_urlsafe: String representation of task key safe for urls.
    """
    _PreventUnauthorizedAccess()
    previous_cursor = self.request.get('error_cursor')
    results, cursor, more = (
        error_reason.ErrorReasonModel.FetchOneUIPageOfErrorsForTask(
            task_key_urlsafe=task_key_urlsafe,
            urlsafe_cursor=previous_cursor))
    self._WriteTemplate(template_file='task_error_reasons', tpl_errors=results,
                        tpl_previous_cursor=previous_cursor, tpl_cursor=cursor,
                        tpl_more=more, tpl_task_key_urlsafe=task_key_urlsafe)


class TaskReportPageHandler(UIBasePageHandler):
  """Handle '/task/report' requests to show user details.

  This page will show summary results from a recall task including
  categories of user_state with counts and user email lists.
  """

  def get(self, task_key_urlsafe):  # pylint: disable=g-bad-name
    """Handler for /task/report get requests.

    Args:
      task_key_urlsafe: String representation of task key safe for urls.
    """
    _PreventUnauthorizedAccess()
    self._WriteTemplate(
        template_file='task_report',
        tpl_task=recall_task.RecallTaskModel.FetchTaskFromSafeId(
            user_domain=view_utils.GetUserDomain(_SafelyGetCurrentUserEmail()),
            task_key_urlsafe=task_key_urlsafe),
        tpl_user_states=domain_user.USER_STATES,
        tpl_message_states=domain_user.MESSAGE_STATES,
        tpl_task_key_urlsafe=task_key_urlsafe)


class TaskUsersPageHandler(UIBasePageHandler):
  """Handle '/task/users' requests to show user details.

  This page will show full lists of users to compare against previous runs.
  """

  def get(self, task_key_urlsafe):  # pylint: disable=g-bad-name
    """Handler for /task/users/debug get requests.

    Args:
      task_key_urlsafe: String representation of task key safe for urls.
    """
    _PreventUnauthorizedAccess()
    previous_cursor = self.request.get('user_cursor')
    results, cursor, more = (
        domain_user.DomainUserToCheckModel.FetchOneUIPageOfUsersForTask(
            task_key_urlsafe=task_key_urlsafe,
            urlsafe_cursor=previous_cursor,
            user_state_filters=self.request.params.getall('user_state'),
            message_state_filters=self.request.params.getall('message_state')))
    self._WriteTemplate(template_file='task_users', tpl_users=results,
                        tpl_previous_cursor=previous_cursor, tpl_cursor=cursor,
                        tpl_more=more, tpl_task_key_urlsafe=task_key_urlsafe)
