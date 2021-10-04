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

import React, { useState } from 'react'
import PropTypes from 'prop-types'
import { connect } from 'react-redux'
import { Link } from 'react-router-dom'
import { Button, Flex, FlexItem, List, ListItem, Title } from '@patternfly/react-core'
import {
  CodeIcon,
  CodeBranchIcon,
  OutlinedCommentDotsIcon,
  CubeIcon,
  FingerprintIcon,
  StreamIcon,
  OutlinedCalendarAltIcon,
  OutlinedClockIcon,
} from '@patternfly/react-icons'
import * as moment from 'moment'
import 'moment-duration-format'

import { buildExternalLink } from '../../Misc'
import { BuildResultBadge, BuildResultWithIcon, IconProperty } from './Misc'
import { ChartModal } from '../charts/ChartModal'
import BuildsetGanttChart from '../charts/GanttChart'

function Buildset({ buildset, timezone, tenant }) {
  const buildset_link = buildExternalLink(buildset)
  const [isGanttChartModalOpen, setIsGanttChartModalOpen] = useState(false)

  const firstStartBuild = buildset.builds.reduce(
    (prev, cur) => (prev.start_time < cur.start_time ? prev : cur)
  )
  const lastEndBuild = buildset.builds.reduce(
    (prev, cur) => (prev.end_time > cur.end_time ? prev : cur)
  )
  const totalDuration = (
    moment.utc(lastEndBuild.end_time).tz(timezone)
    - moment.utc(firstStartBuild.start_time).tz(timezone)) / 1000

  const buildLink = (build) => (
    <Link
      to={`${tenant.linkPrefix}/build/${build.uuid}`}
    >
      {build.job_name}
    </Link>
  )
  const firstStartLink = buildLink(firstStartBuild)
  const lastEndLink = buildLink(lastEndBuild)

  return (
    <>
      <Title headingLevel="h2">
        <BuildResultWithIcon result={buildset.result} size="md">
          Buildset result
        </BuildResultWithIcon>
        <BuildResultBadge result={buildset.result} />
      </Title>
      {/* We handle the spacing for the body and the flex items by ourselves
            so they go hand in hand. By default, the flex items' spacing only
            affects left/right margin, but not top or bottom (which looks
            awkward when the items are stacked at certain breakpoints) */}
      <Flex className="zuul-build-attributes">
        <Flex flex={{ default: 'flex_1' }}>
          <FlexItem>
            <List style={{ listStyle: 'none' }}>
              {/* TODO (felix): It would be cool if we could differentiate
                  between the SVC system (Github, Gitlab, Gerrit), so we could
                  show the respective icon here (GithubIcon, GitlabIcon,
                  GitIcon - AFAIK the Gerrit icon is not very popular among
                  icon frameworks like fontawesome */}
              {buildset_link && (
                <IconProperty
                  WrapElement={ListItem}
                  icon={<CodeIcon />}
                  value={buildset_link}
                />
              )}
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
                  buildset.branch ? (
                    <>
                      <strong>Branch </strong> {buildset.branch}
                    </>
                  ) : (
                    <>
                      <strong>Ref </strong> {buildset.ref}
                    </>
                  )
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
                icon={<OutlinedCalendarAltIcon />}
                value={
                  <span>
                    <strong>Starting build </strong>
                    {firstStartLink} <br />
                    <i>(started {moment
                      .utc(firstStartBuild.start_time)
                      .tz(timezone)
                      .format('YYYY-MM-DD HH:mm:ss')})</i>
                    <br />
                    <strong>Ending build </strong>
                    {lastEndLink} <br />
                    <i>(ended {moment
                      .utc(lastEndBuild.end_time)
                      .tz(timezone)
                      .format('YYYY-MM-DD HH:mm:ss')})</i>
                  </span>
                }
              />
              <IconProperty
                WrapElement={ListItem}
                icon={<OutlinedClockIcon />}
                value={
                  <>
                    <strong>Total duration </strong>
                    {moment
                      .duration(totalDuration, 'seconds')
                      .format('h [hr] m [min] s [sec]')} &nbsp;
                    <Button
                      key='GanttChartToggle'
                      variant='secondary'
                      onClick={() => { setIsGanttChartModalOpen(true) }}>Show timeline
                    </Button>
                  </>
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
      <ChartModal
        chart={<BuildsetGanttChart builds={buildset.builds} />}
        isOpen={isGanttChartModalOpen}
        title='Builds Timeline'
        onClose={() => { setIsGanttChartModalOpen(false) }}
      />
    </>
  )
}

Buildset.propTypes = {
  buildset: PropTypes.object,
  tenant: PropTypes.object,
  timezone: PropTypes.string,
}

export default connect((state) => ({
  tenant: state.tenant,
  timezone: state.timezone,
}))(Buildset)
