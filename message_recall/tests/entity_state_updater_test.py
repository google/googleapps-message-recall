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

"""Unit tests for the EntityStateUpdater class.

Tests that entity states can be updated correctly in the AppEngine datastore.
"""

import unittest

# setup_path required to allow imports from models.
import setup_path  # pylint: disable=unused-import,g-bad-import-order

from models.domain_user import DomainUserToCheckModel
from models.domain_user import MESSAGE_FOUND
from models.domain_user import MESSAGE_UNKNOWN
from models.domain_user import USER_STARTED
from models.entity_state_updater import EntityStateUpdater
from models.recall_task import RecallTaskModel
from models.recall_task import TASK_GETTING_USERS
from models.recall_task import TASK_STARTED
from test_utils import SetupLogging

from google.appengine.ext import testbed


_OWNER_EMAIL = 'testuser@mydomain.com'
_MESSAGE_CRITERIA = (
    'ZZZ33ETLNd8dkrJcNJN1qDE-cOU69xVm1iZgurm37V31EoO9SZz@mail.gmail.com')


def _CreateRecallTaskEntity(owner_email, message_criteria):
  return RecallTaskModel(owner_email=owner_email,
                         message_criteria=message_criteria).put()


def _CreateDomainUserEntity(task_key_id, user_email):
  return DomainUserToCheckModel(recall_task_id=task_key_id,
                                user_email=user_email).put()


def _GetRecallTaskEntity(task_key):
  return RecallTaskModel.query(RecallTaskModel.key == task_key).get()


def _GetDomainUserEntity(user_key):
  return DomainUserToCheckModel.query(
      DomainUserToCheckModel.key == user_key).get()


class EntityStateUpdaterTests(unittest.TestCase):

  def setUp(self):
    SetupLogging()
    self._testbed = testbed.Testbed()
    self._testbed.activate()
    self._testbed.init_datastore_v3_stub()
    self._testbed.init_memcache_stub()

    self._task_key = _CreateRecallTaskEntity(_OWNER_EMAIL, _MESSAGE_CRITERIA)
    self._user_key = _CreateDomainUserEntity(self._task_key.id(),
                                             user_email=_OWNER_EMAIL)

  def tearDown(self):
    self._testbed.deactivate()

  def testCanSetTaskState(self):
    self.assertEqual(TASK_STARTED,
                     _GetRecallTaskEntity(self._task_key).task_state)
    state_updater = EntityStateUpdater(task_key_id=self._task_key.id(),
                                       user_key_id=self._user_key.id())
    state_updater.SetTaskState(TASK_GETTING_USERS)
    self.assertEqual(TASK_GETTING_USERS,
                     _GetRecallTaskEntity(self._task_key).task_state)

  def testCanSetUserState(self):
    self.assertEqual(USER_STARTED,
                     _GetDomainUserEntity(self._user_key).user_state)
    state_updater = EntityStateUpdater(task_key_id=self._task_key.id(),
                                       user_key_id=self._user_key.id())
    state_updater.SetMessageState(MESSAGE_FOUND)
    self.assertEqual(MESSAGE_FOUND,
                     _GetDomainUserEntity(self._user_key).message_state)

  def testCanSetMessageState(self):
    self.assertEqual(MESSAGE_UNKNOWN,
                     _GetDomainUserEntity(self._user_key).message_state)
    state_updater = EntityStateUpdater(task_key_id=self._task_key.id(),
                                       user_key_id=self._user_key.id())
    state_updater.SetMessageState(MESSAGE_FOUND)
    self.assertEqual(MESSAGE_FOUND,
                     _GetDomainUserEntity(self._user_key).message_state)


if __name__ == '__main__':
  unittest.main()
