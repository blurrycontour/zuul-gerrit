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
import { parse } from 'query-string'
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

import { fetchBuildAllInfo } from '../actions/build'
import { fetchLogfile } from '../actions/logfile'
import { EmptyPage } from '../containers/Errors'
import { Fetchable, Fetching } from '../containers/Fetching'
import ArtifactList from '../containers/build/Artifact'
import Build from '../containers/build/Build'
import BuildOutput from '../containers/build/BuildOutput'
import Console from '../containers/build/Console'
import Manifest from '../containers/build/Manifest'
import LogFile from '../containers/logfile/LogFile'

class BuildPage extends React.Component {
  static propTypes = {
    match: PropTypes.object.isRequired,
    build: PropTypes.object,
    isFetching: PropTypes.bool.isRequired,
    isFetchingManifest: PropTypes.bool.isRequired,
    isFetchingOutput: PropTypes.bool.isRequired,
    tenant: PropTypes.object.isRequired,
    fetchBuildAllInfo: PropTypes.func.isRequired,
    activeTab: PropTypes.string.isRequired,
    location: PropTypes.object.isRequired,
    history: PropTypes.object.isRequired,
  }

  updateData = () => {
    // The related fetchBuild...() methods won't do anything if the data is
    // already available in the local state, so just call them.
    this.props.fetchBuildAllInfo(
      this.props.tenant,
      this.props.match.params.buildId,
      this.props.match.params.file
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
        // task summary
        history.push(`${tenant.linkPrefix}/build/${build.uuid}`)
    }
  }

  handleBreadcrumbItemClick = () => {
    // Simply link back to the logs tab without an active logfile
    this.handleTabClick('logs', this.props.build)
  }

  render() {
    const {
      build,
      logfile,
      isFetching,
      isFetchingManifest,
      isFetchingOutput,
      isFetchingLogfile,
      activeTab,
      history,
      location,
      tenant,
    } = this.props
    const hash = location.hash.substring(1).split('/')
    const severity = parseInt(parse(location.search).severity)

    // Get the logfile from react-routers URL parameters
    const logfileName = this.props.match.params.file

    if (!build && isFetching) {
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
      <Fetchable isFetching={isFetching} fetchCallback={this.updateData} />
    )

    const resultsTabContent =
      !build.hosts && isFetchingOutput ? (
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

    let logsTabContent = null
    if (!build.manifest && isFetchingManifest) {
      logsTabContent = <Fetching />
    } else if (logfileName) {
      logsTabContent = (
        <LogFile
          logfileContent={logfile}
          logfileName={logfileName}
          isFetching={isFetchingLogfile}
          // We let the LogFile component itself handle the severity default
          // value in case it's not set via the URL.
          severity={severity ? severity : undefined}
          handleBreadcrumbItemClick={this.handleBreadcrumbItemClick}
          location={location}
          history={history}
        />
      )
    } else if (build.manifest) {
      logsTabContent = <Manifest tenant={this.props.tenant} build={build} />
    } else {
      logsTabContent = (
        <EmptyState variant={EmptyStateVariant.small}>
          <EmptyStateIcon icon={FileCodeIcon} />
          <Title headingLevel="h4" size="lg">
            This build does not provide any logs
          </Title>
        </EmptyState>
      )
    }

    const consoleTabContent =
      !build.output && isFetchingOutput ? (
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
                  <TabTitleText>Task Summary</TabTitleText>
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

function mapStateToProps(state, ownProps) {
  const buildId = ownProps.match.params.buildId
  const build =
    buildId && Object.keys(state.build.builds).length > 0
      ? state.build.builds[buildId]
      : null
  const logfileName = ownProps.match.params.file
  const logfile =
    logfileName && Object.keys(state.logfile.files).length > 0
      ? state.logfile.files[buildId][logfileName]
      : null
  return {
    build,
    logfile,
    tenant: state.tenant,
    isFetching: state.build.isFetching,
    isFetchingManifest: state.build.isFetchingManifest,
    isFetchingOutput: state.build.isFetchingOutput,
    isFetchingLogfile: state.logfile.isFetching,
  }
}

const mapDispatchToProps = { fetchBuildAllInfo, fetchLogfile }

export default connect(
  mapStateToProps,
  mapDispatchToProps
)(withRouter(BuildPage))
