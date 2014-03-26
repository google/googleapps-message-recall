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

"""Handler test for /about.

Tests that the /about link functions.
"""

# setup_path required to allow imports from models.
import setup_path  # pylint: disable=unused-import,g-bad-import-order

import app_handler_test_base
import frontend_views

import webapp2
import webtest


_ABOUT_STRING = 'This application is a tool to delete Email messages'


class AppAboutHandlerTest(app_handler_test_base.AppHandlerTestBase):

  def setUp(self):
    super(AppAboutHandlerTest, self).setUp()
    self._testapp = webtest.TestApp(webapp2.WSGIApplication([
        (r'/about', frontend_views.AboutPageHandler),
        ], debug=True))

  def tearDown(self):
    super(AppAboutHandlerTest, self).tearDown()

  def testAboutHandler(self):
    response = self._testapp.get('/about')
    self.assertEqual(response.status_int, 200)
    self.assertEqual(response.content_type, 'text/html')
    self.assertResponseBodyBeginsWith(response, '<!doctype html>')
    self.assertResponseBodyEndsWith(response, '</body> </html>')
    self.assertResponseBodyContains(response, _ABOUT_STRING)
