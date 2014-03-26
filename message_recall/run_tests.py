#!/usr/bin/python
# Copyright 2014 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Test runner for GAE unit tests."""

import argparse
import os
import sys

import unittest2


def _ParseArgs(argv):
  """Handle command line args unique to this script.

  Args:
    argv: holds all the command line args passed.

  Returns:
    argparser args object with attributes set based on arg settings.
  """
  argparser = argparse.ArgumentParser(description=('Run unit tests for App'
                                                   'Engine app.'))
  argparser.add_argument('--sdk_path', required=True,
                         help='Path to the GAE SDK [REQUIRED].')
  argparser.add_argument('--verbose', '-v', action='store_true', default=False,
                         help='Enable listing of individual test names.')
  args = argparser.parse_args(argv)

  if not os.path.isdir(args.sdk_path):
    argparser.error('Cannot find GAE SDK at %s.' % args.sdk_path)
  sys.path.insert(0, args.sdk_path)
  import dev_appserver  # pylint: disable=g-import-not-at-top
  dev_appserver.fix_sys_path()

  return args


def main(argv):
  args = _ParseArgs(argv)
  suite = unittest2.loader.TestLoader().discover(
      start_dir=os.path.join(os.path.dirname(__file__), 'tests'),
      pattern='*_test.py')
  # 1: Does not show individual test names.
  # 2: Shows individual test names.
  show_test_names = 2 if args.verbose else 1
  unittest2.TextTestRunner(verbosity=show_test_names).run(suite)


if __name__ == '__main__':
  main(sys.argv[1:])
