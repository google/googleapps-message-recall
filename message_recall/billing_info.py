# Copyright 2016 Google Inc. All Rights Reserved.
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

"""Functions to query billing info using the Google API."""

from apiclient.discovery import build
import credentials_utils
import log_utils


_LOG = log_utils.GetLogger('messagerecall.billing_info')


class BillingInfo(object):
  """Class to retrieve billing info.

  Uses http_utils to add error handling and retry using backoff.
  """

  def __init__(self, owner_email):
    """Initialize the billing client.

    Args:
      owner_email: String email address of the project admin.
    """
    self._http = credentials_utils.GetAuthorizedHttp(owner_email)

    # Have seen the following error from build():
    # 'DeadlineExceededError: The API call urlfetch.Fetch() took too long '
    # 'to respond and was cancelled.'
    billing_service = build('cloudbilling', 'v1', http=self._http)
    self._project_collection = billing_service.projects()

  def _GetProjectBillingInfo(self, project_name):
    """Retrieve cloud billing info for a project.

    Args:
      project_name: unique name of a project (hyphens not spaces).

    Returns:
      Object with billing info attributes included billingEnabled.
    """
    resource_name = 'projects/%s' % project_name
    request = self._project_collection.getBillingInfo(name=resource_name)
    return request.execute(http=self._http)

  def IsProjectBillingEnabled(self, project_name):
    """Check if billing enabled for a cloud project.

    Args:
      project_name: unique name of a project (hyphens not spaces).

    Returns:
      True if billing enabled else False.
    """
    billing_info = self._GetProjectBillingInfo(project_name)
    return billing_info.get('billingEnabled', False)
