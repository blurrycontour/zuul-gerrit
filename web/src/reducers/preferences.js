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

import {
  PREFERENCE_SET,
} from '../actions/preferences'


const stored_prefs = localStorage.getItem('preferences')
let default_prefs
if (stored_prefs === null) {
  default_prefs = {
    autoReload: true,
    darkMode: false
  }
} else {
  default_prefs = JSON.parse(stored_prefs)
}

export default (state = {
  ...default_prefs
}, action) => {
  let newstate
  switch (action.type) {
    case PREFERENCE_SET:
      newstate = { ...state, [action.key]: action.value }
      localStorage.setItem('preferences', JSON.stringify(newstate))
      return newstate
    default:
      // We need to update DOM for dark mode upon loading
      // because we cannot handle it by state
      if (state.darkMode) {
        document.documentElement.classList.add('pf-theme-dark')
      } else {
        document.documentElement.classList.remove('pf-theme-dark')
      }
      return state
  }
}
