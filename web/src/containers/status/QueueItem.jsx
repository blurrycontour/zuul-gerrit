// Copyright 2024 BMW Group
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
import { Link } from 'react-router-dom'
import { connect } from 'react-redux'

import {
  Card,
  CardActions,
  CardTitle,
  CardBody,
  CardHeader,
  DataList,
  DataListCell,
  DataListItem,
  DataListItemCells,
  DataListItemRow,
  Dropdown,
  DropdownItem,
  ExpandableSection,
  KebabToggle,
} from '@patternfly/react-core'
import {
  AngleDoubleUpIcon,
  BanIcon,
} from '@patternfly/react-icons'

import {
  calculateQueueItemTimes,
  ChangeLink,
  getRefs,
  JobLink,
  JobResultOrStatus,
} from './Misc'

import QueueItemProgress from './QueueItemProgress'

function QueueItem({ item, tenant }) {
  const [isOpen, setIsOpen] = useState(false)
  const [isJobsExpanded, setIsJobsExpanded] = useState(false)

  const onJobsToggle = (isExpanded) => {
    setIsJobsExpanded(isExpanded)
  }

  const onSelect = () => {
    setIsOpen(!isOpen)
  }

  const showDequeueModal = () => {
    // TODO (felix): Implement
  }

  const showCancelModal = () => {
    // TODO (felix): Implement
  }

  const times = calculateQueueItemTimes(item)

  const dropdownItems = [
    <DropdownItem
      key="dequeue"
      icon={<BanIcon style={{
        color: 'var(--pf-global--danger-color--100)',
      }} />}
      description="Stop all jobs for this change"
      onClick={showDequeueModal()}
    >
      Dequeue
    </DropdownItem>,
    <DropdownItem
      key="promote"
      icon={<AngleDoubleUpIcon style={{
        color: 'var(--pf-global--default-color--200)',
      }} />}
      description="Promote this change to the top of the queue"
      onClick={showCancelModal()}
    >
      Promote
    </DropdownItem>
  ]

  const renderJobList = (jobs) => {
    return (
      <DataList isCompact className="zuul-job-list">
        {jobs.map((job, idx) => (
          <DataListItem key={idx}>
            <DataListItemRow>
              <DataListItemCells
                dataListCells={[
                  <DataListCell key={`${job.name}-name`}>
                    <JobLink job={job} tenant={tenant} />
                  </DataListCell>,
                  <DataListCell isFilled={false} alignRight key={`${job.name}-result`}>
                    {/* TODO (felix): Since the job.name is not unique anymore,
                        this should be looked up by job.uuid */}
                    <JobResultOrStatus job={job} job_times={times.jobs[job.name]} />
                  </DataListCell>
                ]}
              />
            </DataListItemRow>
          </DataListItem>
        ))}
      </DataList>
    )
  }

  return (
    <>
      <Card isCompact className={`zuul-compact-card ${item.live === true ? 'zuul-queue-item' : ''}`}>
        <CardHeader>
          {item.live === true ?
            <CardActions>
              <Dropdown
                onSelect={onSelect}
                toggle={<KebabToggle onToggle={setIsOpen} />}
                isOpen={isOpen}
                isPlain
                dropdownItems={dropdownItems}
                position={'right'}
                style={{ width: '28px' }}
              />
            </CardActions>
            : ''}
          <CardTitle>
            {getRefs(item).map((change, idx) => (
              <div key={idx}>
                {change.project} <ChangeLink change={change} />
              </div>
            ))}
          </CardTitle>
        </CardHeader>
        {item.live === true ?
          <CardBody>
            <QueueItemProgress item={item} times={times} />
            <Link
              to={tenant.linkPrefix + '/status/change/' + getRefs(item)[0].id}
              className="zuul-change-link"
            >
              Show details
            </Link>
            {item.jobs.length > 0 ?
              <ExpandableSection className="zuul-compact-expendable-section"
                toggleContent={isJobsExpanded ? 'Hide jobs' : 'Show jobs'}
                onToggle={onJobsToggle}
                isExpanded={isJobsExpanded}
              >
                {renderJobList(item.jobs)}
              </ExpandableSection>
              : ''}
          </CardBody>
          : ''}
      </Card >
    </>
  )
}

QueueItem.propTypes = {
  item: PropTypes.object,
  tenant: PropTypes.object,
}

export default connect((state) => ({ tenant: state.tenant }))(QueueItem)
