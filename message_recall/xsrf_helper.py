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

"""A helper class to wrangle the xsrf utilities, and provide more logging."""

from log_utils import GetLogger
from oauth2client import appengine
from oauth2client import xsrfutil

from google.appengine.api import memcache


_CACHE_NAMESPACE = 'gmr_xsrf_%s#ns'  # Includes replaced 'action_id'.
_LOG = GetLogger('messagerecall.xsrf_helper')


def _BuildCacheNamespace(action_id):
  """Helper to build memcache namespace strings with the action_id.

  Args:
    action_id: String identifier of the action for which authorization
               is requested.

  Returns:
    The constructed memcache namespace string.
  """
  return _CACHE_NAMESPACE % str(action_id)


class XsrfHelper(object):
  """A helper class to wrangle the xsrf utilities, and provide more logging."""

  @staticmethod
  def GenerateXsrfToken(user_email, action_id):
    """Generate a xsrf token.

    Args:
      user_email: String email address of the form user@domain.com.
      action_id: String identifier of the action for which authorization
                 is requested.

    Returns:
      A string of the xsrf token.
    """
    _LOG.info('Generating xsrf token for %s.', user_email)
    xsrf_token = xsrfutil.generate_token(key=appengine.xsrf_secret_key(),
                                         user_id=user_email,
                                         action_id=action_id)
    _LOG.debug('Successfully generated xsrf token for %s.', user_email)
    return xsrf_token

  @staticmethod
  def GetXsrfToken(user_email, action_id):
    xsrf_token = memcache.get(user_email,
                              namespace=_BuildCacheNamespace(action_id))
    if not xsrf_token:
      xsrf_token = XsrfHelper.GenerateXsrfToken(user_email, action_id)
      memcache.set(user_email, xsrf_token, time=xsrfutil.DEFAULT_TIMEOUT_SECS,
                   namespace=_BuildCacheNamespace(action_id))
    return xsrf_token

  @staticmethod
  def _IsXsrfTokenWellFormedAndNotExpired(user_email, action_id, xsrf_token):
    """Determine if the submitted xsrf token is well-formed and has not expired.

    By well-formed, we mean if the the submitted xsrf token can be decoded and
    will match the generated xsrf token using the same criteria (i.e. check
    forgery).

    The xsrfutil validate_token() method enforces a default token timeout of
    1 hour (60 seconds).

    Args:
      user_email: String email address of the form user@domain.com.
      action_id: String identifier of the action for which authorization
                 is requested.
      xsrf_token: A string of the xsrf token.

    Returns:
      A boolean, True if the token is well-formed and has not expired.
          Otherwise, False.
    """
    is_xsrf_token_well_formed_and_not_expired = xsrfutil.validate_token(
        key=appengine.xsrf_secret_key(), token=xsrf_token,
        user_id=user_email, action_id=action_id)
    _LOG.debug('Is xsrf token well-formed and not expired for %s: %s',
               user_email, is_xsrf_token_well_formed_and_not_expired)
    return is_xsrf_token_well_formed_and_not_expired

  @staticmethod
  def _IsSubmittedXsrfTokenMatchingSavedXsrfToken(user_email, action_id,
                                                  submitted_xsrf_token):
    """Determine if the submitted xsrf token matches the xsrf token in session.

    Args:
      user_email: String email address of the form user@domain.com.
      action_id: String identifier of the action for which authorization
                 is requested.
      submitted_xsrf_token: A string of the submitted xsrf token.

    Returns:
      A boolean, True if submitted xsrf token matches the xsrf token in session.
          Otherwise, False.
    """
    if submitted_xsrf_token == XsrfHelper.GetXsrfToken(user_email, action_id):
      _LOG.debug('Submitted xsrf token matches the saved xsrf token for %s.',
                 user_email)
      return True
    else:
      _LOG.debug('Submitted xsrf token does not match the saved xsrf token '
                 'for %s.', user_email)
      return False

  @staticmethod
  def IsXsrfTokenValid(user_email, action_id, submitted_xsrf_token):
    """Performs various checks to see if the submitted xsrf token is valid.

    Args:
      user_email: String email address of the form user@domain.com.
      action_id: String identifier of the action for which authorization
                 is requested.
      submitted_xsrf_token: A string of the submitted xsrf token.

    Returns:
      A boolean, True if submitted xsrf token is valid.  Otherwise, False.
    """
    return (
        XsrfHelper._IsXsrfTokenWellFormedAndNotExpired(
            user_email, action_id, submitted_xsrf_token) and
        XsrfHelper._IsSubmittedXsrfTokenMatchingSavedXsrfToken(
            user_email, action_id, submitted_xsrf_token))
