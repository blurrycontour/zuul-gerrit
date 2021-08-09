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
import { connect, useDispatch } from 'react-redux'
import {
  Flex,
  FlexItem,
  List,
  ListItem,
  Title,
  Button,
  Modal,
  ModalVariant,
  PageSection,
  PageSectionVariants
} from '@patternfly/react-core'
import {
  CodeIcon,
  CodeBranchIcon,
  OutlinedCommentDotsIcon,
  CubeIcon,
  FingerprintIcon,
  StreamIcon,
  RedoAltIcon,
  // BullhornIcon
} from '@patternfly/react-icons'

import { buildExternalLink, IconProperty } from '../../Misc'
import { BuildResultBadge, BuildResultWithIcon } from './Misc'
import { enqueue, enqueue_ref } from '../../api'
import { addNotification, addApiError } from '../../actions/notifications'


function Buildset({ buildset, tenant, user }) {
  const buildset_link = buildExternalLink(buildset)

  const [showEnqueueModal, setShowEnqueueModal] = useState(false)
  const dispatch = useDispatch()

  function renderEnqueueButton() {
    return (
      <div style={{
        cursor: 'pointer',
        color: 'var(--pf-global--primary-color--100)'
      }}
        title="Re-enqueue this change"
        onClick={(event) => {
          event.preventDefault()
          setShowEnqueueModal(true)
        }}
      >
        <RedoAltIcon /> &nbsp;
        RE-ENQUEUE &nbsp;
      </div>
    )
  }

  function enqueueConfirm() {
    let changeId = buildset.change ? buildset.change + ',' + buildset.patchset : buildset.newrev
    setShowEnqueueModal(false)
    if (/^[0-9a-f]{40}$/.test(changeId)) {
      const oldrev = '0000000000000000000000000000000000000000'
      enqueue_ref(tenant.apiPrefix, buildset.project, buildset.pipeline, buildset.ref, oldrev, changeId, user.token)
        .then(() => {
          dispatch(addNotification(
            {
              text: 'Change queued successfully.',
              type: 'success',
              status: '',
              url: '',
            }))
        })
        .catch(error => {
          dispatch(addApiError(error))
        })
    } else {
      enqueue(tenant.apiPrefix, buildset.project, buildset.pipeline, changeId, user.token)
        .then(() => {
          dispatch(addNotification(
            {
              text: 'Change queued successfully.',
              type: 'success',
              status: '',
              url: '',
            }))
        })
        .catch(error => {
          dispatch(addApiError(error))
        })
    }
  }

  function renderEnqueueModal() {
    let changeId = buildset.change ? buildset.change + ',' + buildset.patchset : buildset.newrev
    const title = 'You are about to re-enqueue a change'
    return (
      <Modal
        variant={ModalVariant.small}
        // titleIconVariant={BullhornIcon}
        isOpen={showEnqueueModal}
        title={title}
        onClose={() => { setShowEnqueueModal(false) }}
        actions={[
          <Button key="deq_confirm" variant="primary" onClick={enqueueConfirm}>Confirm</Button>,
          <Button key="deq_cancel" variant="link" onClick={() => { setShowEnqueueModal(false) }}>Cancel</Button>,
        ]}>
        <p>Please confirm that you want to re-enqueue <strong>all jobs</strong> for change <strong>{changeId}</strong> (project <strong>{buildset.project}</strong>) on pipeline <strong>{buildset.pipeline}</strong>.</p>
      </Modal>
    )
  }

  return (
    <>
      <Title headingLevel="h2">
        <BuildResultWithIcon result={buildset.result} size="md">
          Buildset result
        </BuildResultWithIcon>
        <BuildResultBadge result={buildset.result} /> &nbsp;
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
      {(user.isAdmin && user.scope.indexOf(tenant.name) !== -1) &&
        <PageSection variant={PageSectionVariants.light}>
          {renderEnqueueButton()}
        </PageSection>}
      {renderEnqueueModal()}
    </>
  )
}

Buildset.propTypes = {
  buildset: PropTypes.object,
  tenant: PropTypes.object,
  user: PropTypes.object,
}

export default connect((state) => ({
  tenant: state.tenant,
  user: state.user,
}))(Buildset)
