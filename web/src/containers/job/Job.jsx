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

import * as React from 'react'
import PropTypes from 'prop-types'
import {
  ListView
} from 'patternfly-react'

import JobVariant from './JobVariant'

class Job extends React.Component {
  static propTypes = {
    job: PropTypes.array.isRequired,
  }

  constructor() {
    super()
    this.listView = React.createRef()
  }

  componentDidMount() {
    this.listView.current.setState({expanded: true})
  }

  render () {
    const { job } = this.props
    return (
      <React.Fragment>
        <h2>{job[0].name}</h2>
        <ListView>
          {job.map((variant, idx) => (
            <JobVariant variant={variant}
                        listRef={idx === 0 ? this.listView : null}
                        key={idx} />
          ))}
        </ListView>
      </React.Fragment>
    )
  }
}

export default Job
