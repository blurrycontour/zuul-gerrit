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
import PropTypes from 'prop-types'
import { connect } from 'react-redux'
import {
  Card,
  CardBody,
  CardTitle,
  EmptyState,
  EmptyStateIcon,
  EmptyStateVariant,
  List,
  ListItem,
  Tab,
  Tabs,
  TabTitleIcon,
  TabTitleText,
  Title,
} from '@patternfly/react-core'
import {
  BuildIcon,
  CodeBranchIcon,
  OutlinedCommentDotsIcon,
  CubeIcon,
  FingerprintIcon,
  GithubIcon,
  StreamIcon,
} from '@patternfly/react-icons'

import { ExternalLink } from '../../Misc'
import BuildList from './BuildList'
import { BuildResultBadge, BuildResultWithIcon, IconProperty } from './Misc'

class Buildset extends React.Component {
  static propTypes = {
    buildset: PropTypes.object,
    tenant: PropTypes.object,
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

  render() {
    const { buildset } = this.props
    const { activeTabKey } = this.state

    // Return the builds list or an empty state if no builds are part of the
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

    return (
      <React.Fragment>
        <Card>
          <CardTitle style={{ fontSize: 'var(--pf-global--FontSize--xl)' }}>
            <BuildResultWithIcon result={buildset.result} size="md">
              Buildset {buildset.uuid}
            </BuildResultWithIcon>
            <BuildResultBadge result={buildset.result} />
          </CardTitle>
          <CardBody>
            <List style={{ listStyle: 'none' }}>
              {/* TODO (felix): Can we differentiate between Github, Gerrit,
                  Gitlab, ... here somehow to show the correct icon? As an
                  alternative we could use a generic git icon instead or the
                  CodeIcon (used for the API link in the navbar) */}
              <IconProperty
                WrapElement={ListItem}
                icon={<GithubIcon />}
                value={
                  <ExternalLink target={buildset.ref_url}>
                    {buildset.change},{buildset.patchset}
                  </ExternalLink>
                }
              />
              {/* TODO (felix): Link to project page in Zuul */}
              <IconProperty
                WrapElement={ListItem}
                icon={<CubeIcon />}
                value={buildset.project}
              />
              <IconProperty
                WrapElement={ListItem}
                icon={<CodeBranchIcon />}
                value={buildset.branch}
              />
              <IconProperty
                WrapElement={ListItem}
                icon={<StreamIcon />}
                value={buildset.pipeline}
              />
              <IconProperty
                WrapElement={ListItem}
                icon={<OutlinedCommentDotsIcon />}
                value={buildset.message}
              />
              <IconProperty
                WrapElement={ListItem}
                icon={<FingerprintIcon />}
                value={`event: ${buildset.event_id}`}
              />
            </List>
          </CardBody>
          <CardBody>
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
          </CardBody>
        </Card>
      </React.Fragment>
    )
  }
}

export default connect((state) => ({ tenant: state.tenant }))(Buildset)
