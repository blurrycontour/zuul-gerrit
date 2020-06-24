// Copyright 2020 BMW Group
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
import { connect } from 'react-redux'
import { Link } from 'react-router-dom'
import {
  DataList,
  DataListCell,
  DataListItem,
  DataListItemRow,
  DataListItemCells,
} from '@patternfly/react-core'
import { OutlinedClockIcon } from '@patternfly/react-icons'
import 'moment-duration-format'
import * as moment from 'moment'

import { BuildResult, BuildResultWithIcon, IconProperty } from './Misc'

class BuildList extends React.Component {
  static propTypes = {
    builds: PropTypes.array,
    tenant: PropTypes.object,
  }

  // TODO (felix): Add a property "isCompact" to be used on the buildresult
  // page. Without this flag we might then even use this (with more
  // information) on the /builds page.

  constructor() {
    super()
    this.state = {
      selectedBuildId: null,
    }
  }

  handleSelectDataListItem = (buildId) => {
    this.setState({
      selectedBuildId: buildId,
    })
  }

  render() {
    const { builds, tenant } = this.props
    const { selectedBuildId } = this.state
    return (
      <DataList
        className="zuul-build-list"
        isCompact
        selectedDataListItemId={selectedBuildId}
        onSelectDataListItem={this.handleSelectDataListItem}
        style={{ fontSize: 'var(--pf-global--FontSize--md)' }}
      >
        {builds.map((build) => (
          <DataListItem key={build.uuid || build.job_name} id={build.uuid}>
            <Link
              to={`${tenant.linkPrefix}/build/${build.uuid}`}
              style={{
                textDecoration: 'none',
                color: build.voting
                  ? 'inherit'
                  : 'var(--pf-global--disabled-color--100)',
              }}
            >
              <DataListItemRow>
                <DataListItemCells
                  dataListCells={[
                    <DataListCell key={build.uuid} width={3}>
                      <BuildResultWithIcon
                        result={build.result}
                        colored={build.voting}
                        size="sm"
                      >
                        {build.job_name}
                        {!build.voting && ' (non-voting)'}
                      </BuildResultWithIcon>
                    </DataListCell>,
                    <DataListCell key={`${build.uuid}-time`}>
                      <IconProperty
                        icon={<OutlinedClockIcon />}
                        value={moment
                          .duration(build.duration, 'seconds')
                          .format('h [hr] m [min] s [sec]')}
                      />
                    </DataListCell>,
                    <DataListCell key={`${build.uuid}-result`}>
                      <BuildResult
                        result={build.result}
                        colored={build.voting}
                      />
                    </DataListCell>,
                  ]}
                />
              </DataListItemRow>
            </Link>
          </DataListItem>
        ))}
      </DataList>
    )
  }
}

export default connect((state) => ({ tenant: state.tenant }))(BuildList)
