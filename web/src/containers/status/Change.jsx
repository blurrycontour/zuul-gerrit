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
  Button,
  Dropdown,
  DropdownItem,
  KebabToggle,
  Modal,
  ModalVariant
} from '@patternfly/react-core'
import {
  AngleDoubleUpIcon,
  BanIcon,
} from '@patternfly/react-icons'
import { dequeue, dequeue_ref, promote } from '../../api'
import { addDequeueError, addPromoteError } from '../../actions/adminActions'

import { addNotification } from '../../actions/notifications'
import { fetchStatusIfNeeded } from '../../actions/status'

import LineAngleImage from '../../images/line-angle.png'
import LineTImage from '../../images/line-t.png'
import ChangePanel from './ChangePanel'


class Change extends React.Component {
  static propTypes = {
    change: PropTypes.object.isRequired,
    queue: PropTypes.object.isRequired,
    expanded: PropTypes.bool.isRequired,
    pipeline: PropTypes.object,
    tenant: PropTypes.object,
    user: PropTypes.object,
    dispatch: PropTypes.func
  }

  state = {
    showDequeueModal: false,
    showPromoteModal: false,
    showAdminActions: false,
  }

  dequeueConfirm = () => {
    const { tenant, user, change, pipeline } = this.props
    let projectName = change.project
    let changeId = change.id || 'N/A'
    let changeRef = change.ref
    this.setState(() => ({ showDequeueModal: false }))
    // post-merge
    if (/^[0-9a-f]{40}$/.test(changeId)) {
      dequeue_ref(tenant.apiPrefix, projectName, pipeline.name, changeRef, user.token)
        .then(() => {
          this.props.dispatch(fetchStatusIfNeeded(tenant))
        })
        .catch(error => {
          this.props.dispatch(addDequeueError(error))
        })
      // pre-merge, ie we have a change id
    } else if (changeId !== 'N/A') {
      dequeue(tenant.apiPrefix, projectName, pipeline.name, changeId, user.token)
        .then(() => {
          this.props.dispatch(fetchStatusIfNeeded(tenant))
        })
        .catch(error => {
          this.props.dispatch(addDequeueError(error))
        })
    } else {
      this.props.dispatch(addNotification({
        url: null,
        status: 'Invalid change ' + changeRef + ' on project ' + projectName,
        text: '',
        type: 'error',
      }))
    }
  }

  dequeueCancel = () => {
    this.setState(() => ({ showDequeueModal: false }))
  }

  renderDequeueModal() {
    const { showDequeueModal } = this.state
    const { change } = this.props
    let projectName = change.project
    let changeId = change.id || change.ref
    const title = 'You are about to dequeue a change'
    return (
      <Modal
        variant={ModalVariant.small}
        // titleIconVariant={BullhornIcon}
        isOpen={showDequeueModal}
        title={title}
        onClose={this.dequeueCancel}
        actions={[
          <Button key="deq_confirm" variant="primary" onClick={this.dequeueConfirm}>Confirm</Button>,
          <Button key="deq_cancel" variant="link" onClick={this.dequeueCancel}>Cancel</Button>,
        ]}>
        <p>Please confirm that you want to cancel <strong>all ongoing builds</strong> on change <strong>{changeId}</strong> for project <strong>{projectName}</strong>.</p>
      </Modal>
    )
  }

  promoteConfirm = () => {
    const { tenant, user, change, pipeline } = this.props
    let changeId = change.id || 'NA'
    this.setState(() => ({ showPromoteModal: false }))
    if (changeId !== 'N/A') {
      promote(tenant.apiPrefix, pipeline.name, [changeId,], user.token)
        .then(() => {
          this.props.dispatch(fetchStatusIfNeeded(tenant))
        })
        .catch(error => {
          this.props.dispatch(addPromoteError(error))
        })
    } else {
      this.props.dispatch(addNotification({
        url: null,
        status: 'Invalid change ' + changeId + ' for promotion',
        text: '',
        type: 'error'
      }))
    }
  }

  promoteCancel = () => {
    this.setState(() => ({ showPromoteModal: false }))
  }

  renderPromoteModal() {
    const { showPromoteModal } = this.state
    const { change } = this.props
    let changeId = change.id || 'N/A'
    const title = 'You are about to promote a change'
    return (
      <Modal
        variant={ModalVariant.small}
        // titleIconVariant={BullhornIcon}
        isOpen={showPromoteModal}
        title={title}
        onClose={this.promoteCancel}
        actions={[
          <Button key="prom_confirm" variant="primary" onClick={this.promoteConfirm}>Confirm</Button>,
          <Button key="prom_cancel" variant="link" onClick={this.promoteCancel}>Cancel</Button>,
        ]}>
        <p>Please confirm that you want to promote change <strong>{changeId}</strong>.</p>
      </Modal>
    )
  }

  renderAdminCommands(idx) {
    const { showAdminActions } = this.state
    const { queue } = this.props
    const dropdownCommands = [
      <DropdownItem
        key="dequeue"
        icon={<BanIcon style={{
          color: 'var(--pf-global--danger-color--100)',
        }} />}
        description="Stop all jobs for this change"
        onClick={(event) => {
          event.preventDefault()
          this.setState(() => ({ showDequeueModal: true }))
        }}
      >Dequeue</DropdownItem>,
      <DropdownItem
        key="promote"
        icon={<AngleDoubleUpIcon style={{
          color: 'var(--pf-global--default-color--200)',
        }} />}
        description="Promote this change to the top of the queue"
        onClick={(event) => {
          event.preventDefault()
          this.setState(() => ({ showPromoteModal: true }))
        }}
      >Promote</DropdownItem>
    ]
    return (
      <Dropdown
        title='Actions'
        isOpen={showAdminActions}
        onSelect={() => {
          this.setState({ showAdminActions: !showAdminActions })
          const element = document.getElementById('toggle-id-' + idx + '-' + queue.uuid)
          element.focus()
        }}
        dropdownItems={dropdownCommands}
        isPlain
        toggle={
          <KebabToggle
            onToggle={(showAdminActions) => {
              this.setState({ showAdminActions })
            }}
            id={'toggle-id-' + idx + '-' + queue.uuid} />
        }
      />
    )

  }


  renderStatusIcon(change) {
    let iconGlyph = 'pficon pficon-ok'
    let iconTitle = 'Succeeding'
    if (change.active !== true) {
      iconGlyph = 'pficon pficon-pending'
      iconTitle = 'Waiting until closer to head of queue to' +
        ' start jobs'
    } else if (change.live !== true) {
      iconGlyph = 'pficon pficon-info'
      iconTitle = 'Dependent change required for testing'
    } else if (change.failing_reasons &&
      change.failing_reasons.length > 0) {
      let reason = change.failing_reasons.join(', ')
      iconTitle = 'Failing because ' + reason
      if (reason.match(/merge conflict/)) {
        iconGlyph = 'pficon pficon-error-circle-o zuul-build-merge-conflict'
      } else {
        iconGlyph = 'pficon pficon-error-circle-o'
      }
    }
    const icon = (
      <span
        className={'zuul-build-status ' + iconGlyph}
        title={iconTitle} />
    )
    if (change.live) {
      return (
        <Link to={this.props.tenant.linkPrefix + '/status/change/' + change.id}>
          {icon}
        </Link>
      )
    } else {
      return icon
    }
  }

  renderLineImg(change, i) {
    let image = LineTImage
    if (change._tree_branches.indexOf(i) === change._tree_branches.length - 1) {
      // Angle line
      image = LineAngleImage
    }
    return <img alt="Line" src={image} style={{ verticalAlign: 'baseline' }} />
  }

  render() {
    const { change, queue, expanded, pipeline, user, tenant } = this.props
    let row = []
    let adminMenuWidth = 15
    let i
    for (i = 0; i < queue._tree_columns; i++) {
      let className = ''
      if (i < change._tree.length && change._tree[i] !== null) {
        className = ' zuul-change-row-line'
      }
      row.push(
        <td key={i} className={'zuul-change-row' + className}>
          {i === change._tree_index ? this.renderStatusIcon(change) : ''}
          {change._tree_branches.indexOf(i) !== -1 ? (
            this.renderLineImg(change, i)) : ''}
        </td>)
    }
    let changeWidth = (user.isAdmin && user.scope.indexOf(tenant.name) !== -1)
      ? 360 - adminMenuWidth - 16 * queue._tree_columns
      : 360 - 16 * queue._tree_columns
    row.push(
      <td key={i + 1}
        className="zuul-change-cell"
        style={{ width: changeWidth + 'px' }}>
        <ChangePanel change={change} globalExpanded={expanded} pipeline={pipeline} />
      </td>
    )
    if (user.isAdmin && user.scope.indexOf(tenant.name) !== -1) {
      row.push(
        <td key={i + 2}
          style={{ verticalAlign: 'top', width: adminMenuWidth + 'px' }}>
          {this.renderAdminCommands(i + 2)}
        </td>
      )
    }

    return (
      <>
        <table className="zuul-change-box" style={{ boxSizing: 'content-box' }}>
          <tbody>
            <tr>{row}</tr>
          </tbody>
        </table>
        {this.renderDequeueModal()}
        {this.renderPromoteModal()}
      </>
    )
  }
}

export default connect(state => ({
  tenant: state.tenant,
  user: state.user,
}))(Change)
