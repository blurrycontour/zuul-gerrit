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
import { withRouter } from 'react-router-dom'
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
  PollIcon,
  ExclamationIcon,
} from '@patternfly/react-icons'

import { EmptyPage } from '../containers/Errors'
import { Fetching } from '../containers/Fetching'
import Build from '../containers/build/Build'
import BuildOutput from '../containers/build/BuildOutput'
import { useTenant, useBuild } from '../hooks.js'


const BuildPage = (prop) => {
  const tenant = prop.tenant
  const build = useBuild(tenant, prop.match.params.buildId)

  const hash = window.location.hash.substring(1).split('/')

  // In case the build is not available yet (before the fetching started) or
  // is currently fetching.
  if (build === undefined || build.length === 0) {
    return <Fetching />
  }

  // The build is null, meaning it couldn't be found.
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

  const handleTabClick = (history, tabIndex) => {
    // Usually tabs should only be used to display content in-page and not link
    // to other pages:
    // "Tabs are used to present a set on tabs for organizing content on a
    // .page. It must always be used together with a tab content component."
    // https://www.patternfly.org/v4/documentation/react/components/tabs
    // But as want to be able to reach every tab's content via a dedicated URL
    // while having the look and feel of tabs, we could hijack this onClick
    // handler to do the link/routing stuff.
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

  const resultsTabContent =
    build.hosts === undefined ? (
      <Fetching />
    ) : build.hosts ? (
      <BuildOutput output={build.hosts} />
    ) : build.error_detail ? (
      <>
      <EmptyState variant={EmptyStateVariant.small}>
        <EmptyStateIcon icon={ExclamationIcon} />
      </EmptyState>
        <p><b>Error:</b> {build.error_detail}</p>
      </>
    ) : (
      <EmptyState variant={EmptyStateVariant.small}>
        <EmptyStateIcon icon={PollIcon} />
        <Title headingLevel="h4" size="lg">
          This build does not provide any results
        </Title>
      </EmptyState>
    )

  return (
    <>
      <PageSection variant={PageSectionVariants.light}>
        <Build build={build} active={prop.activeTab} hash={hash} />
      </PageSection>
      <PageSection variant={PageSectionVariants.light}>
        <Tabs
          isFilled
          activeKey={prop.activeTab}
          onSelect={(event, tabIndex) => handleTabClick(prop.history, tabIndex)}
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
        </Tabs>
      </PageSection>
    </>
  )
}

const BuildPageTenant = (prop) => {
  const tenant = useTenant()
  // Wait for the tenant to be set before showing the build page
  return tenant ? <BuildPage {...prop} tenant={tenant} /> : <></>
}

export default withRouter(BuildPageTenant)
