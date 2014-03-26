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

"""Handler test for /.

Tests that the / link functions.
"""

# setup_path required to allow imports from models.
import setup_path  # pylint: disable=unused-import,g-bad-import-order

import app_handler_test_base
import frontend_views

import webapp2
import webtest


_LANDING_STRING = 'Welcome to the Message Recall Application.'


class AppLandingHandlerTest(app_handler_test_base.AppHandlerTestBase):

  def setUp(self):
    super(AppLandingHandlerTest, self).setUp()
    self._testapp = webtest.TestApp(webapp2.WSGIApplication([
        (r'/', frontend_views.LandingPageHandler),
        ], debug=True))

  def tearDown(self):
    super(AppLandingHandlerTest, self).tearDown()

  def testLandingHandler(self):
    response = self._testapp.get('/')
    self.assertEqual(response.status_int, 200)
    self.assertEqual(response.content_type, 'text/html')
    self.assertResponseBodyBeginsWith(response, '<!doctype html>')
    self.assertResponseBodyEndsWith(response, '</body> </html>')
    self.assertResponseBodyContains(response, _LANDING_STRING)
