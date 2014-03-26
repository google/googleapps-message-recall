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

"""Gmail interface using IMAP and Service Accounts.

The usage pattern for GmailInterface is:
  Connect()
  if CheckIfMessageExists(msg_id):
    DeleteMessage(msg_id)
  Disconnect()
"""

import imaplib
import logging

from credentials_utils import GetUserAccessToken
from log_utils import GetLogger
from models.domain_user import MESSAGE_DELETE_FAILED
from models.domain_user import MESSAGE_FOUND
from models.domain_user import MESSAGE_NOT_FOUND
from models.domain_user import MESSAGE_PURGED
from models.domain_user import MESSAGE_VERIFIED_PURGED
from models.domain_user import MESSAGE_VERIFY_FAILED
from models.domain_user import USER_CONNECT_FAILED
from models.domain_user import USER_DONE
from models.domain_user import USER_IMAP_DISABLED
from models.domain_user import USER_RECALLING
from models.entity_state_updater import EntityStateUpdater
from recall_errors import MessageRecallGmailError


_IMAP_DISABLED_STRING = 'IMAP access is disabled for your domain.'
_LOG = GetLogger('messagerecall.gmail', logging.INFO)
_MAX_IMAP_CONNECTION_ATTEMPTS = 2


class GmailHelper(object):
  """Abstracts Gmail operations for page handlers.

  Implemented as a context manager to support 'with ...' semantics.

  Uses GmailInterface and updates user state in the data store to reflect the
  success of the Gmail operations.
  """

  def __init__(self, task_key_id, user_key_id, user_email, message_criteria):
    """Creates useful state updater.

    Args:
      task_key_id: Int unique id of the parent task.
      user_key_id: Int unique id of the user entity to update state.
      user_email: String reflecting the user email being accessed.
      message_criteria: String criteria (message-id) to recall.
    """
    self._state_updater = EntityStateUpdater(task_key_id=task_key_id,
                                             user_key_id=user_key_id)
    self._state_updater.SetUserState(new_state=USER_RECALLING)
    self._gmail = GmailInterface()
    self._user_email = user_email
    self._message_criteria = message_criteria

  def __enter__(self):
    """Wraps GmailInterface.Connect() with state updates.

    Returns:
      True if success else False.
    """
    if self._gmail.Connect(self._user_email):
      return self

    gmail_error_string = str(self.GetLastError())
    if _IMAP_DISABLED_STRING in gmail_error_string:
      new_state = USER_IMAP_DISABLED
    else:
      new_state = USER_CONNECT_FAILED
    self._state_updater.SetUserState(new_state=new_state)
    raise MessageRecallGmailError('Connection Error: %s.' % gmail_error_string)

  def CheckIfMessageExists(self):
    """Wraps GmailInterface.CheckIfMessageExists() with state updates.

    Returns:
      True if the search found at least one matching message.
    """
    result = self._gmail.CheckIfMessageExists(self._message_criteria)
    new_state = MESSAGE_FOUND if result else MESSAGE_NOT_FOUND
    self._state_updater.SetMessageState(new_state=new_state)
    return result

  def DeleteMessage(self):
    """Wraps GmailInterface.DeleteMessage() with state updates.

    Returns:
      True if message successfully purged and verified else False.
    """
    new_state = MESSAGE_DELETE_FAILED
    if self._gmail.DeleteMessage(self._message_criteria):
      self._state_updater.SetMessageState(new_state=MESSAGE_PURGED)
      if self._gmail.CheckIfMessageExists(self._message_criteria):
        new_state = MESSAGE_VERIFY_FAILED
      else:
        new_state = MESSAGE_VERIFIED_PURGED
    self._state_updater.SetMessageState(new_state=new_state)
    return new_state == MESSAGE_VERIFIED_PURGED

  def GetLastError(self):
    """Helper to retrieve last error info if any."""
    return self._gmail.GetLastError()

  def __exit__(self, exc_type, exc_value, exc_traceback):
    """Wraps GmailInterface.Disconnect() with state updates.

    Supplies exception information in case Exception suppression is desired.

    Args:
      exc_type: Type of Exception if an Exception to be raised.
      exc_value: Value of Exception if an Exception to be raised.
      exc_traceback: To be used in Exception processing.
    """
    self._gmail.Disconnect()
    self._state_updater.SetUserState(new_state=USER_DONE)


class GmailInterface(object):
  """Organizes access against mail server.

  Initially uses IMAP. Will use Gmail API when one is invented.
  """

  _AUTH_STRING = 'user=%s\1auth=Bearer %s\1\1'
  # Modify this variable to the appropriate 'Trash' label. In the U.S., it
  # should be 'Trash'. In the U.K. it should be 'Bin'.
  _LOCALIZED_TRASH_LABEL = 'Trash'
  _SEARCH_MESSAGE_ID = '(HEADER Message-ID "%s")'
  _SERVER_ADDRESS = 'imap.gmail.com'
  _SERVER_PORT = 993
  _DEBUG_LEVEL = 0  # 0-5: 0=default, 5=verbose.

  def __init__(self):
    self._found_indices = {}
    self._gmail_labels = ['[Gmail]/All Mail', '[Gmail]/Spam']
    self._imap_query = imaplib.IMAP4_SSL(self._SERVER_ADDRESS,
                                         self._SERVER_PORT)
    self._imap_query.debug = self._DEBUG_LEVEL
    self._label_selected = None
    self._last_error = None
    self._user_email = None

  def _SelectLabel(self, gmail_label):
    """Selects a folder/label for work. This is active state in the connection.

    Args:
      gmail_label: String label/tag of the Gmail folder to activate.
    """
    # Have observed the following error from select():
    # 'socket error: EOF'
    self._imap_query.select(gmail_label)
    self._label_selected = gmail_label

  def _WasMessageFound(self):
    """Determines if any messages were found by looking for found indices.

    Returns:
      True if any messages were found otherwise returns False.
    """
    return bool([bool(x) for x in self._found_indices.values() if x])

  def Connect(self, user_email):
    """Connect to the mail server.

    Args:
      user_email: String reflecting the user email being accessed.

    Returns:
      True if success else False.
    """
    connection_attempts = 1
    force_refresh = False
    while True:
      access_token = GetUserAccessToken(user_email, force_refresh)
      auth_string = self._AUTH_STRING % (user_email, access_token)
      try:
        # Have seen the following errors from authenticate():
        # 'DeadlineExceededError: The API call remote_socket.Receive() took '
        # 'too long to respond and was cancelled'
        #
        # 'SSLError: [Errno 2] _ssl.c:1392: The operation did not complete '
        # '(read)'
        self._imap_query.authenticate('XOAUTH2', lambda x: auth_string)
        self._user_email = user_email
      except imaplib.IMAP4.error as e:
        if str(e) == '[ALERT] Invalid credentials (Failure)':
          if connection_attempts < _MAX_IMAP_CONNECTION_ATTEMPTS:
            _LOG.info('[%s] Connection problem with IMAP. Refreshing token.',
                      user_email)
            force_refresh = True
            connection_attempts += 1
            continue
        _LOG.error('[%s] Error connecting to IMAP: %s.', user_email, e)
        self._last_error = e
      break

    if self._user_email:
      _LOG.debug('[%s] Connected to imap.', self._user_email)
      self._last_error = None
      return True
    return False

  def CheckIfMessageExists(self, message_criteria):
    """Search for a message based on message_criteria.

    By default, we want to search for the message in the All Mail folder since
    all messages live there. IMAP does not allow us to search for a message in
    the entire mailbox but luckily Gmail has the "All Mail" folder.
    We also search for the message in the Spam label since spam messages do not
    show up in All Mail.

    Args:
      message_criteria: String criteria for a search (e.g. message-id).

    Returns:
      True if the search found at least one matching message.
    """
    for gmail_label in self._gmail_labels:
      _LOG.debug('[%s] Searching label %s', self._user_email, gmail_label)
      self._found_indices[gmail_label] = []
      self._SelectLabel(gmail_label)
      search_query = self._SEARCH_MESSAGE_ID % message_criteria
      unused_type, data = self._imap_query.uid('SEARCH', None, search_query)
      found_indices = data[0].split()
      found_count = len(found_indices)
      if found_count > 0:
        if found_count > 1:
          _LOG.warning('[%s] Found %s matches in %s.', self._user_email,
                       found_count, gmail_label)
        self._found_indices[gmail_label] = found_indices
        _LOG.debug('[%s] Found messages in %s: %s.', self._user_email,
                   gmail_label, found_indices)
    return self._WasMessageFound()

  def DeleteMessage(self, message_criteria):
    """Find and delete the message described by message_id.

    Args:
      message_criteria: String criteria for a search (e.g. message-id).

    Returns:
      True if message successfully purged else False.
    """
    _LOG.debug('[%s] Deleting messsage: %s.', self._user_email,
               message_criteria)
    for gmail_label, found_indices in self._found_indices.iteritems():
      if not found_indices:
        continue
      self._SelectLabel(gmail_label)
      for message_index in found_indices:
        self._imap_query.uid('COPY', message_index,
                             '[Gmail]/' + self._LOCALIZED_TRASH_LABEL)
        self._imap_query.expunge()
      _LOG.debug('[%s] %s messages purged from %s.', self._user_email,
                 found_indices, gmail_label)

    gmail_label = '[Gmail]/' + self._LOCALIZED_TRASH_LABEL
    self._SelectLabel(gmail_label)
    messages_found = 0
    search_query = self._SEARCH_MESSAGE_ID % message_criteria
    unused_type, data = self._imap_query.uid('SEARCH', None, search_query)
    for found_index in data[0].split():
      messages_found += 1
      self._imap_query.uid('STORE', found_index, '+FLAGS', '\\Deleted')
      self._imap_query.expunge()
      _LOG.debug('[%s] Message has been purged from Gmail', self._user_email)
    _LOG.debug('[%s] Total message(s) purged: %s', self._user_email,
               messages_found)
    return messages_found > 0

  def Disconnect(self):
    """Close connections to mailbox and mail server."""
    if self._user_email:
      if self._label_selected:
        self._imap_query.close()  # Assumes select() was run.
        self._label_selected = None
      self._imap_query.logout()
      _LOG.debug('[%s] Disconnected from imap.', self._user_email)
      self._user_email = None

  def GetLastError(self):
    """Helper to retrieve last error info if any."""
    return self._last_error
