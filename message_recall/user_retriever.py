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

"""Functions to search users using the Google Admin SDK API."""

import httplib

from apiclient.discovery import build
from apiclient.errors import HttpError
import credentials_utils
import log_utils


_LOG = log_utils.GetLogger('messagerecall.user_retriever')
_MAX_RESULT_PAGE_SIZE = 500  # Default is 100.


class DomainUserRetriever(object):
  """Class to organize large, multi-page user searches.

  Uses http_utils to add error handling and retry using backoff.
  """

  def __init__(self, owner_email, user_domain, search_query):
    """Initialize the search class.

    Build the items needed to page through domain user lists which are expected
    to be >100k users at times.  Need a users collection object from the ADMIN
    SDK to reference the search api and an authenticated http connection to
    invoke it.

    Args:
      owner_email: String email address of the user who owns the task.
      user_domain: String domain for our apps domain.
      search_query: Admin SDK search query string (e.g. 'email:%s*' % const).
    """
    self._http = credentials_utils.GetAuthorizedHttp(owner_email)
    self._user_domain = user_domain
    self._search_query = search_query

    # Have seen the following error from build():
    # 'DeadlineExceededError: The API call urlfetch.Fetch() took too long '
    # 'to respond and was cancelled.'
    directory_service = build('admin', 'directory_v1')
    self._users_collection = directory_service.users()

  def _FetchUserListPage(self, next_page_token=None):
    """Helper that handles exceptions retrieving pages of users.

    Args:
      next_page_token: Used for ongoing paging of users.

    Returns:
      List of users retrieved (one page with default page size: 100 users).
    """
    # 'deleted' users are not examined.
    # https://developers.google.com/admin-sdk/directory/v1/reference/users/list
    request = self._users_collection.list(domain=self._user_domain,
                                          maxResults=_MAX_RESULT_PAGE_SIZE,
                                          query=self._search_query,
                                          pageToken=next_page_token)
    # Not infrequently seeing:
    # 'HTTPException: Deadline exceeded while waiting for HTTP response '
    # 'from URL: https://www.googleapis.com/admin/directory/v1/users'
    # '?query=email%3A6%2A&domain=capgsfishing.com&alt=json&maxResults=500'
    # Default socket timeout seems to be 5s so increasing it to 10s
    # in GetAuthorizedHttp() seems to have helped.
    return request.execute(http=self._http)

  def GetUserAttributes(self, user_email):
    """Helper to retrieve user attributes from the Admin SDK API.

    Args:
      user_email: String email address of the form user@domain.com.

    Returns:
      Dictionary of user_attributes discovered.

    Raises:
      MessageRecallError: If unable to execute the API call.
    """
    request = self._users_collection.get(userKey=user_email)
    try:
      return request.execute(
          http=credentials_utils.GetAuthorizedHttp(user_email))
    except (HttpError, httplib.HTTPException) as e:
      if e.resp.status == 403:  # If user is not an admin...
        return {}
      raise

  def GetUserAttribute(self, user_email, attribute_tag):
    """Helper to retrieve one user attribute using the Admin SDK API.

    Args:
      user_email: String email address of the form user@domain.com.
      attribute_tag: String tag of the attribute to retrieve.

    Returns:
      Dictionary value of the user_attribute or None.
    """
    return self.GetUserAttributes(user_email).get(attribute_tag)

  def RetrieveDomainUsers(self):
    """Retrieves domain user list page by page and allows iteration of users.

    Yields:
      List of Strings: user emails of the next page of users or [].
    """
    next_page_token = None
    while True:
      users_list = self._FetchUserListPage(next_page_token=next_page_token)
      yield [(user['primaryEmail'], user['suspended'])
             for user in users_list.get('users', [])]
      next_page_token = users_list.get('nextPageToken')
      if not next_page_token:
        break
