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
  Flex,
  FlexItem,
  List,
  ListItem,
  Title,
} from '@patternfly/react-core'
import {
  BookIcon,
  BuildIcon,
  CodeBranchIcon,
  CodeIcon,
  CubeIcon,
  FileCodeIcon,
  FingerprintIcon,
  HistoryIcon,
  OutlinedCalendarAltIcon,
  OutlinedClockIcon,
  StreamIcon,
} from '@patternfly/react-icons'
import * as moment from 'moment'
import 'moment-duration-format'

import { BuildResultBadge, BuildResultWithIcon, IconProperty } from './Misc'
import { ExternalLink } from '../../Misc'

function Build(props) {
  const { build, tenant, timezone, fetchable } = props
  return (
    <>
      <Title
        headingLevel="h2"
        style={{
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
        {fetchable}
      </Title>
      {/* We handle the spacing for the body and the flex items by ourselves
          so they go hand in hand. By default, the flex items' spacing only
          affects left/right margin, but not top or bottom (which looks
          awkward when the items are stacked at certain breakpoints) */}
      <Flex className="zuul-build-attributes">
        <Flex flex={{ lg: 'flex_1' }}>
          <FlexItem>
            <List style={{ listStyle: 'none' }}>
              {/* TODO (felix): What should we show for periodic builds
                  here? They don't provide a change, but the ref_url is
                  also not usable */}
              {build.change && (
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
              )}
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
                  build.branch ? (
                    <>
                      <strong>Branch </strong> {build.branch}
                    </>
                  ) : (
                    <>
                      <strong>Ref </strong> {build.ref}
                    </>
                  )
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
        <Flex flex={{ lg: 'flex_1' }}>
          <FlexItem>
            <List style={{ listStyle: 'none' }}>
              <IconProperty
                WrapElement={ListItem}
                icon={<OutlinedCalendarAltIcon />}
                value={
                  <span>
                    <strong>Started at </strong>
                    {moment
                      .utc(build.start_time)
                      .tz(timezone)
                      .format('YYYY-MM-DD HH:mm:ss')}
                    <br />
                    <strong>Completed at </strong>
                    {moment
                      .utc(build.end_time)
                      .tz(timezone)
                      .format('YYYY-MM-DD HH:mm:ss')}
                  </span>
                }
              />
              <IconProperty
                WrapElement={ListItem}
                icon={<OutlinedClockIcon />}
                value={
                  <>
                    <strong>Took </strong>
                    {moment
                      .duration(build.duration, 'seconds')
                      .format('h [hr] m [min] s [sec]')}
                  </>
                }
              />
            </List>
          </FlexItem>
        </Flex>
        <Flex flex={{ lg: 'flex_1' }}>
          <FlexItem>
            <List style={{ listStyle: 'none' }}>
              <IconProperty
                WrapElement={ListItem}
                icon={<BookIcon />}
                value={
                  <Link to={tenant.linkPrefix + '/job/' + build.job_name}>
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
                      tenant.linkPrefix +
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
              {/* In some cases not all build data is available on initial
                      page load (e.g. when we come from another page like the
                      buildset result page). Thus, we have to check for the
                      buildset here. */}
              {build.buildset && (
                <IconProperty
                  WrapElement={ListItem}
                  icon={<BuildIcon />}
                  value={
                    <Link
                      to={
                        tenant.linkPrefix + '/buildset/' + build.buildset.uuid
                      }
                    >
                      View buildset result
                    </Link>
                  }
                />
              )}
              <IconProperty
                WrapElement={ListItem}
                icon={<FileCodeIcon />}
                value={
                  build.log_url ? (
                    <ExternalLink target={build.log_url}>View log</ExternalLink>
                  ) : (
                    <span
                      style={{
                        color: 'var(--pf-global--disabled-color--100)',
                      }}
                    >
                      No log available
                    </span>
                  )
                }
              />
            </List>
          </FlexItem>
        </Flex>
      </Flex>
    </>
  )
}

Build.propTypes = {
  build: PropTypes.object,
  tenant: PropTypes.object,
  hash: PropTypes.array,
  timezone: PropTypes.string,
  fetchable: PropTypes.node,
}

export default connect((state) => ({
  tenant: state.tenant,
  timezone: state.timezone,
}))(Build)
