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
  Flex,
  FlexItem,
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
  CodeIcon,
  CodeBranchIcon,
  OutlinedCommentDotsIcon,
  CubeIcon,
  FingerprintIcon,
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
              Buildset result
            </BuildResultWithIcon>
            <BuildResultBadge result={buildset.result} />
          </CardTitle>
          <CardBody>
            <Flex>
            <Flex flex={{ default: 'flex_1' }}>
              <FlexItem>
                <List style={{ listStyle: 'none' }}>
                  {/* TODO (felix): It would be cool if we could differentiate
                    between the SVC system (Github, Gitlab, Gerrit), so we could
                    show the respective icon here (GithubIcon, GitlabIcon,
                    GitIcon - AFAIK the Gerrit icon is not very popular among
                    icon frameworks like fontawesome */}
                  <IconProperty
                    WrapElement={ListItem}
                    icon={<CodeIcon />}
                    value={
                      <ExternalLink target={buildset.ref_url}>
                        <strong>Change </strong>
                        {buildset.change},{buildset.patchset}
                      </ExternalLink>
                    }
                  />
                  {/* TODO (felix): Link to project page in Zuul */}
                  <IconProperty
                    WrapElement={ListItem}
                    icon={<CubeIcon />}
                    value={
                      <>
                        <strong>Project </strong> {buildset.project}
                      </>
                    }
                  />
                  <IconProperty
                    WrapElement={ListItem}
                    icon={<CodeBranchIcon />}
                    value={
                      <>
                        <strong>Branch </strong> {buildset.branch}
                      </>
                    }
                  />
                  <IconProperty
                    WrapElement={ListItem}
                    icon={<StreamIcon />}
                    value={
                      <>
                        <strong>Pipeline </strong> {buildset.pipeline}
                      </>
                    }
                  />
                  <IconProperty
                    WrapElement={ListItem}
                    icon={<FingerprintIcon />}
                    value={
                      <span>
                        <strong>UUID </strong> {buildset.uuid} <br />
                        <strong>Event ID </strong> {buildset.event_id} <br />
                      </span>
                    }
                  />
                </List>
              </FlexItem>
              </Flex>
              <Flex flex={{ default: 'flex_1' }}>
              <FlexItem>
                <List style={{ listStyle: 'none' }}>
                  <IconProperty
                    WrapElement={ListItem}
                    icon={<OutlinedCommentDotsIcon />}
                    value={
                      <>
                        <strong>Message:</strong>
                        <pre>{buildset.message}</pre>
                      </>
                    }
                  />
                </List>
              </FlexItem>
            </Flex>
            </Flex>
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
