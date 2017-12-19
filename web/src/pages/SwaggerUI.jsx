// Copyright 2018 Red Hat, Inc
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
import SwaggerUi from 'swagger-ui'
import 'swagger-ui/dist/swagger-ui.css'

import { getHomepageUrl } from '../api'


class SwaggerUI extends React.Component {
  constructor() {
    super()
    this.url = getHomepageUrl() + 'swagger.json'
  }

  componentDidMount() {
    SwaggerUi({
      dom_id: '#swaggerContainer',
      url: this.url,
      presets: [SwaggerUi.presets.apis]
    })
  }

  render() {
    return <div id="swaggerContainer" />
  }
}

export default SwaggerUI;
