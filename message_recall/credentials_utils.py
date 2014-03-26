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

"""Utility functions to retrieve OAuth2 credentials using a service account.

A service account is used to allow multiple 'Admin' users access to resources
owned by multiple users in an apps domain.
"""

import os

import http_utils
import log_utils
from oauth2client import client
import recall_errors
import service_account

from google.appengine.api import memcache


_ACCESS_TOKEN_CACHE_S = 60 * 59  # Access tokens last about 1 hour.
_CACHE_NAMESPACE = 'messagerecall_accesstoken#ns'
_LOG = log_utils.GetLogger('messagerecall.credentials_utils')

# Load the key in PKCS 12 format that you downloaded from the Google API
# Console when you created your Service account.
_SERVICE_ACCOUNT_PEM_FILE_NAME = os.path.join(
    os.path.dirname(__file__), 'messagerecall_privatekey.pem')

with open(_SERVICE_ACCOUNT_PEM_FILE_NAME, 'rb') as f:
  _SERVICE_ACCOUNT_KEY = f.read()


def _GetSignedJwtAssertionCredentials(user_email):
  """Retrieve an OAuth2 credentials object impersonating user_email.

  This object is then used to authorize an http connection that will be
  used to connect with Google services such as the Admin SDK.
  Also includes an access_token that is used to connect to IMAP.

  The first parameter, service_account_name,is the Email address
  created for the Service account from the API Console.  The sub parameter
  is the Authenticated user to impersonate.

  Args:
    user_email: String of the user email account to impersonate.

  Returns:
    oauth2client credentials object.
  """
  return client.SignedJwtAssertionCredentials(
      service_account_name=service_account.SERVICE_ACCOUNT_NAME,
      private_key=_SERVICE_ACCOUNT_KEY,
      scope=service_account.SERVICE_SCOPES,
      sub=user_email)


def GetAuthorizedHttp(user_email):
  """Establish authorized http connection needed for API access.

  All authorizations via service account rely on an initial authorized
  connection using a domain admin. Authorized http connections are needed
  for Google Apiary API access and an authorized access_token is needed
  for IMAP access.

  Credentials objects come with an empty access_token by default. To avoid
  quota issues with the oauth server, we manage access_tokens in the memcache.
  If we didn't update the access_token, every credentials.authorize() would
  force a round-trip with the oauth server.

  Args:
    user_email: String of the authorizing user email account.

  Returns:
    Authorized http connection able to access Google API services.
  """
  credentials = _GetSignedJwtAssertionCredentials(user_email)
  credentials.access_token = GetUserAccessToken(user_email)
  return credentials.authorize(http_utils.GetHttpObject())


def GetUserAccessToken(user_email, force_refresh=False):
  """Helper to get a refreshed access_token for a user via service account.

  Args:
    user_email: User email for which access_token will be retrieved.
    force_refresh: Boolean, if True force a token refresh.

  Returns:
    Cached access_token or a new one.
  """
  access_token = memcache.get(user_email, namespace=_CACHE_NAMESPACE)
  if access_token and not force_refresh:
    return access_token

  credentials = _GetSignedJwtAssertionCredentials(user_email)
  # Have observed the following error from refresh():
  # 'Unable to fetch URL: https://accounts.google.com/o/oauth2/token'
  _LOG.debug('Refreshing access token for %s.', user_email)
  credentials.refresh(http_utils.GetHttpObject())
  access_token = credentials.access_token
  if memcache.set(user_email, access_token, time=_ACCESS_TOKEN_CACHE_S,
                  namespace=_CACHE_NAMESPACE):
    return access_token
  raise recall_errors.MessageRecallCounterError(
      'Exceeded retry limit in GetUserAccessToken: %s.' % user_email)
