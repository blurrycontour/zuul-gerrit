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
import { connect, useDispatch } from 'react-redux'

import {
  Button,
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
  Modal,
  ModalVariant,
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

import { dequeue, dequeue_ref, promote } from '../../api'
import { addDequeueError, addPromoteError } from '../../actions/adminActions'
import { addNotification } from '../../actions/notifications'
import { fetchStatusIfNeeded } from '../../actions/status'

function JobList({ jobs, tenant, job_times }) {
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
                  <JobResultOrStatus job={job} job_times={job_times[job.name]} />
                </DataListCell>
              ]}
            />
          </DataListItemRow>
        </DataListItem>
      ))}
    </DataList>
  )
}

JobList.propTypes = {
  jobs: PropTypes.array.isRequired,
  tenant: PropTypes.object.isRequired,
  job_times: PropTypes.object.isRequired,
}

function DequeueModal({ item, isOpen, onConfirm, onCancel }) {
  const ref = getRefs(item)[0]
  let projectName = ref.project
  let refId = ref.id || ref.ref
  return (
    <Modal
      variant={ModalVariant.small}
      isOpen={isOpen}
      title="You are about to dequeue a change"
      onClose={onCancel}
      actions={[
        <Button key="deq_confirm" variant="primary" onClick={onConfirm}>
          Confirm
        </Button>,
        <Button key="deq_cancel" variant="link" onClick={onCancel}>
          Cancel
        </Button>,
      ]}>
      <p>
        Please confirm that you want to cancel <strong>all ongoing builds</strong> on
        change <strong>{refId}</strong> for project <strong>{projectName}</strong>.
      </p>
    </Modal>
  )
}

DequeueModal.propTypes = {
  item: PropTypes.object.isRequired,
  isOpen: PropTypes.bool.isRequired,
  onConfirm: PropTypes.func.isRequired,
  onCancel: PropTypes.func.isRequired,
}


function PromoteModal({ item, isOpen, onConfirm, onCancel }) {
  const ref = getRefs(item)[0]
  let refId = ref.id || 'N/A'
  return (
    <Modal
      variant={ModalVariant.small}
      isOpen={isOpen}
      title="You are about to promote a change"
      onClose={onCancel}
      actions={[
        <Button key="prom_confirm" variant="primary" onClick={onConfirm}>
          Confirm
        </Button>,
        <Button key="prom_cancel" variant="link" onClick={onCancel}>
          Cancel
        </Button>,
      ]}
    >
      <p>Please confirm that you want to promote a change <strong>{refId}</strong>.</p>
    </Modal>
  )
}

PromoteModal.propTypes = {
  item: PropTypes.object.isRequired,
  isOpen: PropTypes.bool.isRequired,
  onConfirm: PropTypes.func.isRequired,
  onCancel: PropTypes.func.isRequired,
}

function QueueItem({ item, pipeline, tenant, user }) {
  const [isAdminActionsOpen, setIsAdminActionsOpen] = useState(false)
  const [isDequeueModalOpen, setIsDequeueModalOpen] = useState(false)
  const [isPromoteModalOpen, setIsPromoteModalOpen] = useState(false)
  const [isJobsExpanded, setIsJobsExpanded] = useState(false)

  const dispatch = useDispatch()

  const onJobsToggle = (isExpanded) => {
    setIsJobsExpanded(isExpanded)
  }

  const onSelect = () => {
    setIsAdminActionsOpen(!isAdminActionsOpen)
  }

  const showDequeueModal = () => {
    setIsDequeueModalOpen(true)
  }

  const showPromoteModal = () => {
    setIsPromoteModalOpen(true)
  }

  const confirmDequeue = () => {
    const ref = getRefs(item)[0]
    // Use the first ref as a proxy for the item since queue
    // commands operate on changes
    let projectName = ref.project
    let refId = ref.id || 'N/A'
    let refRef = ref.ref

    // close the modal
    setIsDequeueModalOpen(false)

    if (/^[0-9a-f]{40}$/.test(refId)) {
      // post-merge with a ref update (tag, branch push)
      dequeue_ref(tenant.apiPrefix, projectName, pipeline.name, refRef)
        .then(() => {
          dispatch(fetchStatusIfNeeded(tenant))
        })
        .catch(error => {
          dispatch(addDequeueError(error))
        })
    } else if (refId !== 'N/A') {
      // pre-merge, ie we have a change id
      dequeue(tenant.apiPrefix, projectName, pipeline.name, refId)
        .then(() => {
          dispatch(fetchStatusIfNeeded(tenant))
        })
        .catch(error => {
          dispatch(addDequeueError(error))
        })
    } else {
      // periodic with only a ref (branch head)
      dequeue_ref(tenant.apiPrefix, projectName, pipeline.name, refRef)
        .then(() => {
          dispatch(fetchStatusIfNeeded(tenant))
        })
        .catch(error => {
          dispatch(addDequeueError(error))
        })
    }
  }

  const confirmPromote = () => {
    const ref = getRefs(item)[0]
    let refId = ref.id || 'NA'

    // close the modal
    setIsPromoteModalOpen(false)

    if (refId !== 'N/A') {
      promote(tenant.apiPrefix, pipeline.name, [refId,])
        .then(() => {
          dispatch(fetchStatusIfNeeded(tenant))
        })
        .catch(error => {
          dispatch(addPromoteError(error))
        })
    } else {
      dispatch(addNotification({
        url: null,
        status: 'Invalid change ' + refId + ' for promotion',
        text: '',
        type: 'error'
      }))
    }
  }

  const cancelDequeue = () => {
    setIsDequeueModalOpen(false)
  }

  const cancelPromote = () => {
    setIsPromoteModalOpen(false)
  }

  const times = calculateQueueItemTimes(item)

  const adminActions = [
    <DropdownItem
      key="dequeue"
      icon={<BanIcon style={{
        color: 'var(--pf-global--danger-color--100)',
      }} />}
      description="Stop all jobs for this change"
      onClick={() => showDequeueModal()}
    >
      Dequeue
    </DropdownItem>,
    <DropdownItem
      key="promote"
      icon={<AngleDoubleUpIcon style={{
        color: 'var(--pf-global--default-color--200)',
      }} />}
      description="Promote this change to the top of the queue"
      onClick={() => showPromoteModal()}
    >
      Promote
    </DropdownItem>
  ]

  return (
    <>
      <Card isCompact className={`zuul-compact-card ${item.live === true ? 'zuul-queue-item' : ''}`}>
        <CardHeader>
          {item.live === true && user.isAdmin && user.scope.indexOf(tenant.name) !== -1 ?
            <CardActions>
              <Dropdown
                onSelect={onSelect}
                toggle={<KebabToggle onToggle={setIsAdminActionsOpen} />}
                isOpen={isAdminActionsOpen}
                isPlain
                dropdownItems={adminActions}
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
            {item.jobs.length > 0 ?
              <ExpandableSection className="zuul-compact-expendable-section"
                toggleContent={isJobsExpanded ? 'Hide jobs' : 'Show jobs'}
                onToggle={onJobsToggle}
                isExpanded={isJobsExpanded}
              >
                <JobList jobs={item.jobs} tenant={tenant} job_times={times.jobs} />
              </ExpandableSection>
              : ''}
          </CardBody>
          : ''}
      </Card >
      <DequeueModal
        item={item}
        isOpen={isDequeueModalOpen}
        onConfirm={confirmDequeue}
        onCancel={cancelDequeue}
      />
      <PromoteModal
        item={item}
        isOpen={isPromoteModalOpen}
        onConfirm={confirmPromote}
        onCancel={cancelPromote}
      />
    </>
  )
}

QueueItem.propTypes = {
  item: PropTypes.object,
  pipeline: PropTypes.object,
  tenant: PropTypes.object,
  user: PropTypes.object,
}

export default connect(state => ({
  tenant: state.tenant,
  user: state.user,
}))(QueueItem)
