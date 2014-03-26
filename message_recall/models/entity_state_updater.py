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

"""Helper class for updating task and user state in the data store."""


from models import domain_user
from models import recall_task


class EntityStateUpdater(object):
  """Simplify entity state update calls when they occur frequently."""

  def __init__(self, task_key_id, user_key_id):
    """Save keys needed to do state updates.

    Args:
      task_key_id: Int unique id of the RecallTaskModel object for this recall.
      user_key_id: Int unique id of the DomainUserToCheckModel object.
    """
    self._task_key_id = int(task_key_id)
    self._user_key_id = int(user_key_id)

  def SetTaskState(self, new_state):
    """Helper to update task state.

    Args:
      new_state: String update for the ndb StringProperty field.
    """
    recall_task.RecallTaskModel.SetTaskState(self._task_key_id, new_state)

  def SetUserState(self, new_state):
    """Helper to update task user state.

    Args:
      new_state: String update for the ndb StringProperty field.
    """
    domain_user.DomainUserToCheckModel.SetUserState(
        self._user_key_id, new_state)

  def SetMessageState(self, new_state):
    """Helper to update task user message state.

    Args:
      new_state: String update for the ndb StringProperty field.
    """
    domain_user.DomainUserToCheckModel.SetMessageState(
        self._user_key_id, new_state)
