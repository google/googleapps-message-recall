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

"""Helper functions for running unit tests."""

import logging
import os
import tempfile


_ENABLE_VERBOSE_LOGGING = False  # Set to True to see debug log messages.


def GetLogFileName():
  """Helper to produce the log file name."""
  return os.path.join(tempfile.gettempdir(), 'google_api_testing.log')


def SetupLogging(verbose_flag=_ENABLE_VERBOSE_LOGGING):
  """Initialize logging and handle --verbose option.

  Args:
    verbose_flag: command line verbose flag.

  Returns:
    Initialized logger.
  """
  if verbose_flag:
    logging_level = logging.DEBUG
    print 'Showing VERBOSE output.'
  else:
    logging_level = logging.INFO

  # Setup logging handler to file of DEBUG+ messages. Messages include
  # timestamp and messages append to the logfile.
  logging.basicConfig(level=logging_level,
                      format='%(asctime)s %(levelname)-8s %(message)s',
                      datefmt='%Y%m%d %H:%M:%S',
                      filename=GetLogFileName(),
                      filemode='a')

  # Setup logging handler to console of INFO+ messages.
  # Use them as PRINT messages.
  console_handler = logging.StreamHandler()
  console_handler.setLevel(logging_level)
  # Set a format which is simpler for console use (no time/date prefix).
  # We do not use multiple-area logging so we do not:
  # a) supply a area-string when acquiring a logger
  # b) show an area-string %(name) in our formatters
  # c) set a global logger since logging.getLogger('') retrieves the same
  #    instance across modules.
  console_formatter = logging.Formatter('%(levelname)-8s %(message)s')
  # tell the handler to use this format
  console_handler.setFormatter(console_formatter)
  # add the handler to the root logger
  logger = logging.getLogger('')
  logger.addHandler(console_handler)
