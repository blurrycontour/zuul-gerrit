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

import React from 'react'
import { Translate, I18n } from 'react-redux-i18n'

// Use in components
function _ (translatable, optionalVars = {}) {
  return (
    <Translate value={translatable} {...optionalVars} />
  )
}

// Use in variables, or component props
function t (translatable, optionalVars = {}) {
  return I18n.t(translatable, optionalVars)
}

export { _, t }
