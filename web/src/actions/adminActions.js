// Copyright 2020 Red Hat, Inc
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may
// not use this file except in compliance with the License. You may obtain
// a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
// WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
// License for the specific language governing permissions and limitations
// under the License.

export const ADMIN_DEQUEUE_FAIL = 'ADMIN_DEQUEUE_FAIL'
export const ADMIN_ENQUEUE_FAIL = 'ADMIN_ENQUEUE_FAIL'
export const ADMIN_AUTOHOLD_FAIL = 'ADMIN_AUTOHOLD_FAIL'
export const ADMIN_PROMOTE_FAIL = 'ADMIN_PROMOTE_FAIL'

export const addDequeueError = error => ({
  type: ADMIN_DEQUEUE_FAIL,
  notification: error
})

export const addEnqueueError = error => ({
  type: ADMIN_ENQUEUE_FAIL,
  notification: error
})

export const addAutoholdError = error => ({
  type: ADMIN_AUTOHOLD_FAIL,
  notification: error
})

export const addPromoteError = error => ({
  type: ADMIN_PROMOTE_FAIL,
  notification: error
})