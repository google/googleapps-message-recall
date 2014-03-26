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

"""Sharded counter implementation: allows high volume counter access.

Reference: https://developers.google.com/appengine/articles/sharding_counters
"""

import random

import log_utils
import recall_errors

from google.appengine.api import memcache
from google.appengine.ext import ndb


_COUNTER_MEMCACHE_EXPIRATION_S = 60 * 60 * 24
_LOG = log_utils.GetLogger('messagerecall.models.sharded_counter')
_SHARD_KEY_TEMPLATE = 'shard-{}-{:d}'
_TRANSACTIONAL_RETRIES = 8


class CounterShardConfig(ndb.Model):
  """Allows customized shard count: highly used counters need more shards."""
  num_shards = ndb.IntegerProperty(default=20)

  @classmethod
  def AllKeys(cls, name):
    """Returns all possible keys for the counter name given the config.

    Args:
      name: The name of the counter.

    Returns:
      The full list of ndb.Key values corresponding to all the possible
      counter shards that could exist.
    """
    config = cls.get_or_insert(name)
    shard_key_strings = [_SHARD_KEY_TEMPLATE.format(name, index)
                         for index in range(config.num_shards)]
    return [ndb.Key(CounterShardCount, shard_key_string)
            for shard_key_string in shard_key_strings]


class CounterShardCount(ndb.Model):
  """Shard count for each named counter."""
  count = ndb.IntegerProperty(default=0)


def GetCounterCount(name):
  """Sums a cumulative value from all the shard counts for the given name.

  Args:
    name: The name of the counter.

  Returns:
    Integer; the cumulative count of all sharded counters for the given
    counter name.
  """
  total = memcache.get(key=name)
  if total is not None:
    return total

  total = 0
  all_keys = CounterShardConfig.AllKeys(name)
  for counter in ndb.get_multi(all_keys):
    if counter is not None:
      total += counter.count
  if memcache.add(key=name, value=total,
                  time=_COUNTER_MEMCACHE_EXPIRATION_S):
    return total
  raise recall_errors.MessageRecallCounterError(
      'Unexpected problem adding to memcache: %s.' % name)


@ndb.transactional
def IncreaseCounterShards(name, num_shards):
  """Increase the number of shards for a given sharded counter.

  Will never decrease the number of shards.

  Args:
    name: The name of the counter.
    num_shards: How many shards to use.
  """
  config = CounterShardConfig.get_or_insert(name)
  if config.num_shards < num_shards:
    config.num_shards = num_shards
    config.put()


@ndb.transactional(retries=_TRANSACTIONAL_RETRIES)
def _Increment(name, num_shards, delta=1):
  """Transactional helper to increment the value for a given sharded counter.

  Also takes a number of shards to determine which shard will be used.

  Retry count bumped up to work through occasional db latency issues.

  Args:
    name: The name of the counter.
    num_shards: How many shards to use.
    delta: Non-negative integer to increment key.

  Returns:
    The new long integer value or None if a problem arose.
  """
  index = random.randint(0, num_shards - 1)
  shard_key_string = _SHARD_KEY_TEMPLATE.format(name, index)
  counter = CounterShardCount.get_by_id(shard_key_string)
  if counter is None:
    counter = CounterShardCount(id=shard_key_string)
  counter.count += delta
  counter.put()
  if delta < 0:
    return memcache.decr(key=name, delta=-delta, initial_value=0)
  return memcache.incr(key=name, delta=delta, initial_value=0)


def IncrementCounterAndGetCount(name, delta=1):
  """Increment the value for a given sharded counter.

  Args:
    name: The name of the counter.
    delta: Non-negative integer to increment key.

  Returns:
    The new long integer value or None if a problem arose.
  """
  if not delta:
    return None
  config = CounterShardConfig.get_or_insert(name)
  return _Increment(name=name, num_shards=config.num_shards, delta=delta)
