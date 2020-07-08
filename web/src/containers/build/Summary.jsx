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
import { connect } from 'react-redux'
import {
  EmptyState,
  EmptyStateIcon,
  EmptyStateVariant,
  Title,
} from '@patternfly/react-core'
import { FileArchiveIcon } from '@patternfly/react-icons'

import ArtifactList from './Artifact'
import BuildOutput from './BuildOutput'

class Summary extends React.Component {
  static propTypes = {
    build: PropTypes.object,
    tenant: PropTypes.object,
    timezone: PropTypes.string,
  }

  render() {
    const { build } = this.props

    const artifactsContent = build.artifacts.length ? (
      <ArtifactList artifacts={build.artifacts} />
    ) : (
      <EmptyState
        className="zuul-empty-artifacts"
        variant={EmptyStateVariant.small}
      >
        <EmptyStateIcon icon={FileArchiveIcon} />
        <Title headingLevel="h4" size="lg">
          This build does not provide any artifacts
        </Title>
      </EmptyState>
    )

    return (
      <React.Fragment>
        <h3>Artifacts</h3>
        {artifactsContent}
        <h3>Results</h3>
        {build.hosts && <BuildOutput output={build.hosts}/>}
      </React.Fragment>
    )
  }
}

export default connect((state) => ({
  tenant: state.tenant,
  timezone: state.timezone,
}))(Summary)
