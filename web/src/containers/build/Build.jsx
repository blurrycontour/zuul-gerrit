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
import { Link } from 'react-router-dom'
import {
  Card,
  CardBody,
  CardTitle,
  Flex,
  FlexItem,
  List,
  ListItem,
  Nav,
  NavList,
  NavItem,
} from '@patternfly/react-core'
import {
  BookIcon,
  BuildIcon,
  ClockIcon,
  CodeBranchIcon,
  CodeIcon,
  CubeIcon,
  FileArchiveIcon,
  FileCodeIcon,
  FingerprintIcon,
  HistoryIcon,
  StopwatchIcon,
  StreamIcon,
  TerminalIcon,
} from '@patternfly/react-icons'
import * as moment from 'moment'
import 'moment-duration-format'

import { BuildResultBadge, BuildResultWithIcon, IconProperty } from './Misc'
import { ExternalLink } from '../../Misc'

class Build extends React.Component {
  static propTypes = {
    build: PropTypes.object,
    active: PropTypes.string,
    tenant: PropTypes.object,
    children: PropTypes.object,
    timezone: PropTypes.string,
  }

  render() {
    const { build, active, timezone, children } = this.props
    // TODO (felix): Test with a periodic build:
    // http://localhost:3000/t/openstack/build/1d3eb5c20e0c48d782d17fcea1e12ff2
    return (
      <>
        <Card>
          <CardTitle
            style={{
              fontSize: 'var(--pf-global--FontSize--xl)',
              color: build.voting
                ? 'inherit'
                : 'var(--pf-global--disabled-color--100)',
            }}
          >
            <BuildResultWithIcon
              result={build.result}
              colored={build.voting}
              size="md"
            >
              {build.job_name} {!build.voting && ' (non-voting)'}
            </BuildResultWithIcon>
            <BuildResultBadge result={build.result} />
          </CardTitle>
          <CardBody>
            <Flex>
              <Flex flex={{ default: 'flex_1' }}>
                <FlexItem>
                  <List style={{ listStyle: 'none' }}>
                    {/* TODO (felix): What should we show for periodic builds
                        here? They don't provide a change, but the ref_url is
                        also not usable */}
                    <IconProperty
                      WrapElement={ListItem}
                      icon={<CodeIcon />}
                      value={
                        <ExternalLink target={build.ref_url}>
                          <strong>Change </strong>
                          {build.change},{build.patchset}
                        </ExternalLink>
                      }
                    />
                    {/* TODO (felix): Link to project page in Zuul */}
                    <IconProperty
                      WrapElement={ListItem}
                      icon={<CubeIcon />}
                      value={
                        <>
                          <strong>Project </strong> {build.project}
                        </>
                      }
                    />
                    <IconProperty
                      WrapElement={ListItem}
                      icon={<CodeBranchIcon />}
                      value={
                        <>
                          <strong>Branch </strong> {build.branch}
                        </>
                      }
                    />
                    <IconProperty
                      WrapElement={ListItem}
                      icon={<StreamIcon />}
                      value={
                        <>
                          <strong>Pipeline </strong> {build.pipeline}
                        </>
                      }
                    />
                    <IconProperty
                      WrapElement={ListItem}
                      icon={<FingerprintIcon />}
                      value={
                        <span>
                          <strong>UUID </strong> {build.uuid} <br />
                          <strong>Event ID </strong> {build.event_id} <br />
                        </span>
                      }
                    />
                  </List>
                </FlexItem>
              </Flex>
              <Flex flex={{ default: 'flex_1' }}>
                <List style={{ listStyle: 'none' }}>
                  <IconProperty
                    WrapElement={ListItem}
                    icon={<ClockIcon />}
                    value={
                      <span>
                        <strong>Start </strong>
                        {moment
                          .utc(build.start_time)
                          .tz(timezone)
                          .format('YYYY-MM-DD HH:mm:ss')}
                        <br />
                        <strong>End </strong>
                        {moment
                          .utc(build.end_time)
                          .tz(timezone)
                          .format('YYYY-MM-DD HH:mm:ss')}
                      </span>
                    }
                  />
                  <IconProperty
                    WrapElement={ListItem}
                    icon={<StopwatchIcon />}
                    value={
                      <>
                        <strong>took </strong>
                        {moment
                          .duration(build.duration, 'seconds')
                          .format('h [hr] m [min] s [sec]')}
                      </>
                    }
                  />
                  <IconProperty
                    WrapElement={ListItem}
                    icon={<BookIcon />}
                    value={
                      <Link
                        to={
                          this.props.tenant.linkPrefix +
                          '/job/' +
                          build.job_name
                        }
                      >
                        View job documentation
                      </Link>
                    }
                  />
                  <IconProperty
                    WrapElement={ListItem}
                    icon={<HistoryIcon />}
                    value={
                      <Link
                        to={
                          this.props.tenant.linkPrefix +
                          '/builds?job_name=' +
                          build.job_name +
                          '&project=' +
                          build.project
                        }
                        title="See previous runs of this job inside current project."
                      >
                        View build history
                      </Link>
                    }
                  />
                  {/* TODO (felix): The Summary.jsx file contained a check for
                      !build.buildset ... -> Could there be builds without a
                      buildset? */}
                  <IconProperty
                    WrapElement={ListItem}
                    icon={<BuildIcon />}
                    value={
                      <Link
                        to={
                          this.props.tenant.linkPrefix +
                          '/buildset/' +
                          build.buildset.uuid
                        }
                      >
                        View buildset result
                      </Link>
                    }
                  />
                  <IconProperty
                    WrapElement={ListItem}
                    icon={<FileCodeIcon />}
                    value={
                      <ExternalLink target={build.log_url}>
                        View log
                      </ExternalLink>
                    }
                  />
                </List>
              </Flex>
            </Flex>
          </CardBody>
          <CardBody>
            <Nav variant="tertiary">
              <NavList>
                <NavItem
                  key="summary"
                  itemId="summary"
                  isActive={active === 'results'}
                >
                  <Link
                    to={this.props.tenant.linkPrefix + '/build/' + build.uuid}
                  >
                    <FileArchiveIcon
                      style={{ marginRight: 'var(--pf-global--spacer--sm)' }}
                    />{' '}
                    Results
                  </Link>
                </NavItem>
                <NavItem key="logs" itemId="logs" isActive={active === 'logs'}>
                  <Link
                    to={
                      this.props.tenant.linkPrefix +
                      '/build/' +
                      build.uuid +
                      '/logs'
                    }
                  >
                    <FileCodeIcon
                      style={{ marginRight: 'var(--pf-global--spacer--sm)' }}
                    />{' '}
                    Logs
                  </Link>
                </NavItem>
                <NavItem
                  key="console"
                  itemId="console"
                  isActive={active === 'console'}
                >
                  <Link
                    to={
                      this.props.tenant.linkPrefix +
                      '/build/' +
                      build.uuid +
                      '/console'
                    }
                  >
                    <TerminalIcon
                      style={{ marginRight: 'var(--pf-global--spacer--sm)' }}
                    />{' '}
                    Console
                  </Link>
                </NavItem>
              </NavList>
            </Nav>
            {children}
          </CardBody>
        </Card>
      </>
    )
  }
}

export default connect((state) => ({
  tenant: state.tenant,
  timezone: state.timezone,
}))(Build)
