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

"""Base class test for frontend/backend Handler."""

import unittest

# setup_path required to allow imports from models.
import setup_path  # pylint: disable=unused-import,g-bad-import-order

import frontend_views
from test_utils import SetupLogging

from google.appengine.ext import testbed


_ADMIN_USER_EMAIL = 'george@altostrat.com'


class AppHandlerTestBase(unittest.TestCase):

  def setUp(self):
    SetupLogging()
    self._testbed = testbed.Testbed()
    self._testbed.activate()
    self._testbed.setup_env(overwrite=True, USER_EMAIL=_ADMIN_USER_EMAIL,
                            USER_ID='1', USER_IS_ADMIN='1')
    self._testbed.init_user_stub()
    self._testbed.init_memcache_stub()

    # Fake the admin checks.
    frontend_views._CacheUserEmailBillingEnabled(_ADMIN_USER_EMAIL)
    frontend_views._CacheUserEmailAsAdmin(_ADMIN_USER_EMAIL)

    # Derived classes need to set this as follows for tests:
    #
    #   self._testapp = webtest.TestApp(webapp2.WSGIApplication([
    #       (r'/about', frontend_views.AboutPageHandler),
    #       ], debug=True))
    self._testapp = None

  def tearDown(self):
    self._testbed.deactivate()

  def assertResponseBodyBeginsWith(self, response, verification_string):
    response_body = response.normal_body.strip()
    self.assertEqual(response_body[:len(verification_string)],
                     verification_string)

  def assertResponseBodyEndsWith(self, response, verification_string):
    response_body = response.normal_body.strip()
    self.assertEqual(
        response_body[len(response_body) - len(verification_string):],
        verification_string)

  def assertResponseBodyContains(self, response, verification_string):
    self.assertIn(verification_string, response.normal_body)
