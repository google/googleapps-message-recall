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

"""Backend handler for Message Recall.

Services requests as a private, dynamic backend.
"""

# setup_path required to allow imports from lib folder.
import setup_path  # pylint: disable=unused-import,g-bad-import-order

import backend_views
import webapp2


app = webapp2.WSGIApplication([
    (r'/_ah/start',
     backend_views.StartBackendHandler),
    (r'/backend/recall_messages',
     backend_views.Phase1RecallMessagesHandler),
    (r'/backend/retrieve_domain_users',
     backend_views.Phase2RetrieveDomainUsersHandler),
    (r'/backend/recall_user_messages',
     backend_views.Phase3RecallUserMessagesHandler),
    (r'/backend/wait_for_task_completion',
     backend_views.Phase4WaitForTaskCompletionHandler),
    ], debug=False)
