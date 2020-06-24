// Copyright 2019 Red Hat, Inc
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
import { connect } from 'react-redux'
import PropTypes from 'prop-types'
import {
  EmptyState,
  EmptyStateIcon,
  EmptyStateVariant,
  PageSection,
  PageSectionVariants,
  Tab,
  Tabs,
  TabTitleIcon,
  TabTitleText,
  Title,
} from '@patternfly/react-core'
import { BuildIcon } from '@patternfly/react-icons'

import { fetchBuildsetIfNeeded } from '../actions/build'
import { EmptyPage } from '../containers/Errors'
import { Fetchable, Fetching } from '../containers/Fetching'
import BuildList from '../containers/build/BuildList'
import Buildset from '../containers/build/Buildset'

class BuildsetPage extends React.Component {
  static propTypes = {
    match: PropTypes.object.isRequired,
    remoteData: PropTypes.object,
    tenant: PropTypes.object,
    dispatch: PropTypes.func,
  }

  constructor() {
    super()
    this.state = {
      activeTabKey: 0,
    }
  }

  handleTabClick = (event, tabIndex) => {
    this.setState({
      activeTabKey: tabIndex,
    })
  }

  updateData = (force) => {
    this.props.dispatch(
      fetchBuildsetIfNeeded(
        this.props.tenant,
        this.props.match.params.buildsetId,
        force
      )
    )
  }

  componentDidMount() {
    document.title = 'Zuul Buildset'
    if (this.props.tenant.name) {
      this.updateData()
    }
  }

  componentDidUpdate(prevProps) {
    if (this.props.tenant.name !== prevProps.tenant.name) {
      this.updateData()
    }
  }

  render() {
    const { remoteData, tenant } = this.props
    const { activeTabKey } = this.state
    const buildset = remoteData.buildsets[this.props.match.params.buildsetId]

    // Initial page load
    if (!buildset && remoteData.isFetching) {
      return <Fetching />
    }

    // Fetching finished, but no buildset found
    if (!buildset) {
      // TODO (felix): Provide some generic error (404?) page. Can we somehow
      // identify the error here?
      return (
        <EmptyPage
          title="This buildset does not exist"
          icon={BuildIcon}
          linkTarget={`${tenant.linkPrefix}/buildsets`}
          linkText="Show all buildsets"
        />
      )
    }

    // Return the build list or an empty state if no builds are part of the
    // buildset.
    const buildsTabContent = buildset.builds ? (
      <BuildList builds={buildset.builds} />
    ) : (
      <EmptyState variant={EmptyStateVariant.small}>
        <EmptyStateIcon icon={BuildIcon} />
        <Title headingLevel="h4" size="lg">
          This buildset does not contain any builds
        </Title>
      </EmptyState>
    )

    const fetchable = (
      <Fetchable
        isFetching={remoteData.isFetching}
        fetchCallback={this.updateData}
      />
    )

    return (
      <>
        <PageSection variant={PageSectionVariants.light}>
          <Buildset buildset={buildset} fetchable={fetchable} />
        </PageSection>
        <PageSection variant={PageSectionVariants.light}>
          <Tabs activeKey={activeTabKey} onSelect={this.handleTabClick}>
            <Tab
              eventKey={0}
              title={
                <>
                  <TabTitleIcon>
                    <BuildIcon />
                  </TabTitleIcon>
                  <TabTitleText>Builds</TabTitleText>
                </>
              }
            >
              {buildsTabContent}
            </Tab>
          </Tabs>
        </PageSection>
      </>
    )
  }
}

export default connect((state) => ({
  tenant: state.tenant,
  remoteData: state.build,
}))(BuildsetPage)
