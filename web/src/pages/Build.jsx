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
import { connect } from 'react-redux'
import { withRouter } from 'react-router-dom'
import PropTypes from 'prop-types'
import {
  EmptyState,
  EmptyStateVariant,
  EmptyStateIcon,
  PageSection,
  PageSectionVariants,
  Tab,
  Tabs,
  TabTitleIcon,
  TabTitleText,
  Title,
} from '@patternfly/react-core'
import {
  BuildIcon,
  FileArchiveIcon,
  FileCodeIcon,
  TerminalIcon,
  PollIcon,
} from '@patternfly/react-icons'

import { fetchBuildIfNeeded } from '../actions/build'
import { EmptyPage } from '../containers/Errors'
import { Fetchable, Fetching } from '../containers/Fetching'
import ArtifactList from '../containers/build/Artifact'
import Build from '../containers/build/Build'
import BuildOutput from '../containers/build/BuildOutput'
import Console from '../containers/build/Console'
import Manifest from '../containers/build/Manifest'

class BuildPage extends React.Component {
  static propTypes = {
    match: PropTypes.object.isRequired,
    remoteData: PropTypes.object,
    tenant: PropTypes.object,
    dispatch: PropTypes.func,
    activeTab: PropTypes.string.isRequired,
    location: PropTypes.object,
    history: PropTypes.object,
  }

  updateData = (force) => {
    this.props.dispatch(
      fetchBuildIfNeeded(
        this.props.tenant,
        this.props.match.params.buildId,
        force
      )
    )
  }

  componentDidMount() {
    document.title = 'Zuul Build'
    if (this.props.tenant.name) {
      this.updateData()
    }
  }

  componentDidUpdate(prevProps) {
    if (this.props.tenant.name !== prevProps.tenant.name) {
      this.updateData()
    }
  }

  handleTabClick = (tabIndex, build) => {
    // Usually tabs should only be used to display content in-page and not link
    // to other pages:
    // "Tabs are used to present a set on tabs for organizing content on a
    // .page. It must always be used together with a tab content component."
    // https://www.patternfly.org/v4/documentation/react/components/tabs
    // But as want to be able to reach every tab's content via a dedicated URL
    // while having the look and feel of tabs, we could hijack this onClick
    // handler to do the link/routing stuff.
    const { history, tenant } = this.props

    switch (tabIndex) {
      case 'artifacts':
        history.push(`${tenant.linkPrefix}/build/${build.uuid}/artifacts`)
        break
      case 'logs':
        history.push(`${tenant.linkPrefix}/build/${build.uuid}/logs`)
        break
      case 'console':
        history.push(`${tenant.linkPrefix}/build/${build.uuid}/console`)
        break
      default:
        // results
        history.push(`${tenant.linkPrefix}/build/${build.uuid}`)
    }
  }

  render() {
    const { remoteData, activeTab, location, tenant } = this.props
    const build = remoteData.builds[this.props.match.params.buildId]
    const hash = location.hash.substring(1).split('/')

    if (!build && remoteData.isFetching) {
      return <Fetching />
    }

    if (!build) {
      return (
        <EmptyPage
          title="This build does not exist"
          icon={BuildIcon}
          linkTarget={`${tenant.linkPrefix}/builds`}
          linkText="Show all builds"
        />
      )
    }

    const fetchable = (
      <Fetchable
        isFetching={remoteData.isFetching}
        fetchCallback={this.updateData}
      />
    )

    const resultsTabContent =
      !build.hosts && remoteData.isFetchingOutput ? (
        <Fetching />
      ) : build.hosts ? (
        <BuildOutput output={build.hosts} />
      ) : (
        <EmptyState variant={EmptyStateVariant.small}>
          <EmptyStateIcon icon={PollIcon} />
          <Title headingLevel="h4" size="lg">
            This build does not provide any results
          </Title>
        </EmptyState>
      )

    const artifactsTabContent = build.artifacts.length ? (
      <ArtifactList artifacts={build.artifacts} />
    ) : (
      <EmptyState variant={EmptyStateVariant.small}>
        <EmptyStateIcon icon={FileArchiveIcon} />
        <Title headingLevel="h4" size="lg">
          This build does not provide any artifacts
        </Title>
      </EmptyState>
    )

    const logsTabContent =
      !build.manifest && remoteData.isFetchingManifest ? (
        <Fetching />
      ) : build.manifest ? (
        <Manifest tenant={this.props.tenant} build={build} />
      ) : (
        <EmptyState variant={EmptyStateVariant.small}>
          <EmptyStateIcon icon={FileCodeIcon} />
          <Title headingLevel="h4" size="lg">
            This build does not provide any logs
          </Title>
        </EmptyState>
      )

    const consoleTabContent =
      !build.output && remoteData.isFetchingOutput ? (
        <Fetching />
      ) : build.output ? (
        <Console
          output={build.output}
          errorIds={build.errorIds}
          displayPath={hash.length > 0 ? hash : undefined}
        />
      ) : (
        <EmptyState variant={EmptyStateVariant.small}>
          <EmptyStateIcon icon={TerminalIcon} />
          <Title headingLevel="h4" size="lg">
            This build does not provide any console information
          </Title>
        </EmptyState>
      )

    return (
      <>
        <PageSection variant={PageSectionVariants.light}>
          <Build
            build={build}
            active={activeTab}
            hash={hash}
            fetchable={fetchable}
          />
        </PageSection>
        <PageSection variant={PageSectionVariants.light}>
          <Tabs
            isFilled
            activeKey={activeTab}
            onSelect={(event, tabIndex) => this.handleTabClick(tabIndex, build)}
          >
            <Tab
              eventKey="results"
              title={
                <>
                  <TabTitleIcon>
                    <PollIcon />
                  </TabTitleIcon>
                  <TabTitleText>Results</TabTitleText>
                </>
              }
            >
              {resultsTabContent}
            </Tab>
            <Tab
              eventKey="artifacts"
              title={
                <>
                  <TabTitleIcon>
                    <FileArchiveIcon />
                  </TabTitleIcon>
                  <TabTitleText>Artifacts</TabTitleText>
                </>
              }
            >
              {artifactsTabContent}
            </Tab>
            <Tab
              eventKey="logs"
              title={
                <>
                  <TabTitleIcon>
                    <FileCodeIcon />
                  </TabTitleIcon>
                  <TabTitleText>Logs</TabTitleText>
                </>
              }
            >
              {logsTabContent}
            </Tab>
            <Tab
              eventKey="console"
              title={
                <>
                  <TabTitleIcon>
                    <TerminalIcon />
                  </TabTitleIcon>
                  <TabTitleText>Console</TabTitleText>
                </>
              }
            >
              {consoleTabContent}
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
}))(withRouter(BuildPage))
