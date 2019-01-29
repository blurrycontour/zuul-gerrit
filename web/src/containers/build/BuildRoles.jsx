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
  Icon,
  ListView,
} from 'patternfly-react'
import * as moment from 'moment'


class BuildRoles extends React.Component {
  static propTypes = {
    roles: PropTypes.array,
  }

  render () {
    const { roles } = this.props
    return (
      <ListView className="zuul-role-list">
        {roles.map((role, idx) => (
          <ListView.Item
            key={idx}
            leftContent={<ListView.Icon name="cube" />}
            heading={role.name}
            additionalInfo={[
              <ListView.InfoItem key="ok" title="Tasks">
                <Icon type='pf' name='info' />
                <strong>{role.count}</strong>
              </ListView.InfoItem>,
              <ListView.InfoItem key="duration" title="Duration">
                <Icon type='fa' name='clock-o' />
                {moment.duration(role.duration, 'ms').humanize(true)}
              </ListView.InfoItem>,
            ]}
          />
        ))}
      </ListView>
    )
  }
}


export default BuildRoles
