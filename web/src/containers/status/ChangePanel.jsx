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
import * as moment from 'moment'
import 'moment-duration-format'

import { Button, Modal, ModalVariant } from '@patternfly/react-core'
import { TrashIcon, BullhornIcon, AngleDoubleUpIcon } from '@patternfly/react-icons'
import { dequeue, dequeue_ref, promote } from '../../api'
import { addDequeueError } from '../../actions/adminActions'
import { fetchStatusIfNeeded } from '../../actions/status'

import { addError } from '../../actions/errors'


class ChangePanel extends React.Component {
  static propTypes = {
    globalExpanded: PropTypes.bool.isRequired,
    change: PropTypes.object.isRequired,
    pipeline: PropTypes.object,
    tenant: PropTypes.object,
    user: PropTypes.object,
    dispatch: PropTypes.func
  }

  constructor () {
    super()
    this.state = {
      expanded: false,
      showDequeueModal: false,
      showPromoteModal: false
    }
    this.onClick = this.onClick.bind(this)
    this.clicked = false
  }

  renderDequeueButton () {
      return (
        <TrashIcon
          title="Dequeue this change"
          style={{cursor:'pointer'}}
          color='#A30000'
          onClick={(event) => {
            event.preventDefault()
            this.setState(() => ({showDequeueModal: true}))
        }} />
      )
  }

  renderPromoteButton () {
      return (
        <AngleDoubleUpIcon
          title="Promote this change"
          style={{cursor:'pointer'}}
          onClick={(event) => {
            event.preventDefault()
            this.setState(() => ({showPromoteModal: true}))
        }} />
      )
  }

  dequeueConfirm = () => {
    const { tenant, user, change, pipeline } = this.props
    let projectName = change.project
    let changeId = change.id || 'N/A'
    let changeRef = change.ref
    this.setState(() => ({showDequeueModal: false}))
    // post-merge
    if (/^[0-9a-f]{40}$/.test(changeId)) {
      dequeue_ref(tenant.apiPrefix, projectName, pipeline.name, changeRef, user.token)
        .catch(error => {
           this.props.dispatch(addDequeueError(error))
        })
    // pre-merge, ie we have a change id
    } else if (changeId !== 'N/A') {
      dequeue(tenant.apiPrefix, projectName, pipeline.name, changeId, user.token)
        .catch(error => {
          this.props.dispatch(addDequeueError(error))
        })
    } else {
        this.props.dispatch(addError({
          url: null,
          status: 'Invalid change ' + changeRef + ' on project ' + projectName,
          text: ''
        }))
    }
  }

  dequeueCancel = () => {
    this.setState(() => ({showDequeueModal: false}))
  }

  promoteConfirm = () => {
    const { tenant, user, change, pipeline } = this.props
    let changeId = change.id || 'NA'
    this.setState(() => ({showPromoteModal: false}))
     if (changeId !== 'N/A') {
      promote(tenant.apiPrefix, pipeline.name, [changeId, ], user.token)
        .then(() => {
            this.props.dispatch(fetchStatusIfNeeded(this.props.tenant))
        })
        .catch(error => {
          alert(error)
        })
    } else {
        this.props.dispatch(addError({
          url: null,
          status: 'Invalid change ' + changeId + ' for promotion',
          text: ''
        }))
    }
  }

  promoteCancel = () => {
    this.setState(() => ({showPromoteModal: false}))
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
        titleIconVariant={BullhornIcon}
        isOpen={showDequeueModal}
        title={title}
        onClose={this.dequeueCancel}
        actions={[
          <Button key="deq_confirm" variant="primary" onClick={this.dequeueConfirm}>Confirm</Button>,
          <Button key="deq_cancel" variant="link" onClick={this.dequeueCancel}>Cancel</Button>,
        ]}>
      <p>Please confirm that you want to cancel <strong>all ongoing builds</strong> on change <strong>{ changeId }</strong> for project <strong>{ projectName }</strong>.</p>
    </Modal>
    )
  }

  renderPromoteModal() {
    const { showPromoteModal } = this.state
    const { change } = this.props
    let changeId = change.id || 'N/A'
    const title = 'You are about to promote a change'
    return (
      <Modal
        variant={ModalVariant.small}
        titleIconVariant={BullhornIcon}
        isOpen={showPromoteModal}
        title={title}
        onClose={this.promoteCancel}
        actions={[
          <Button key="prom_confirm" variant="primary" onClick={this.promoteConfirm}>Confirm</Button>,
          <Button key="prom_cancel" variant="link" onClick={this.promoteCancel}>Cancel</Button>,
        ]}>
      <p>Please confirm that you want to promote change <strong>{ changeId }</strong>.</p>
    </Modal>
    )
  }

  onClick (e) {
    // Skip middle mouse button
    if (e.button === 1) {
      return
    }
    let expanded = this.state.expanded
    if (!this.clicked) {
      expanded = this.props.globalExpanded
    }
    this.clicked = true
    this.setState({ expanded: !expanded })
  }

  time (ms) {
    return moment.duration(ms).format({
      template: 'h [hr] m [min]',
      largest: 2,
      minValue: 1,
      usePlural: false,
    })
  }

  enqueueTime (ms) {
    // Special format case for enqueue time to add style
    let hours = 60 * 60 * 1000
    let now = Date.now()
    let delta = now - ms
    let status = 'text-success'
    let text = this.time(delta)
    if (delta > (4 * hours)) {
      status = 'text-danger'
    } else if (delta > (2 * hours)) {
      status = 'text-warning'
    }
    return <span className={status}>{text}</span>
  }

  jobStrResult (job) {
    let result = job.result ? job.result.toLowerCase() : null
    if (result === null) {
      if (job.url === null) {
        if (job.queued === false) {
          result = 'waiting'
        } else {
          result = 'queued'
        }
      } else if (job.paused !== null && job.paused) {
        result = 'paused'
      } else {
        result = 'in progress'
      }
    }
    return result
  }

  renderChangeLink (change) {
    let changeId = change.id || 'NA'
    let changeTitle = changeId
    // Fall back to display the ref if there is no change id
    if (changeId === 'NA' && change.ref) {
      changeTitle = change.ref
    }
    let changeText = ''
    if (change.url !== null) {
      let githubId = changeId.match(/^([0-9]+),([0-9a-f]{40})$/)
      if (githubId) {
        changeTitle = githubId
        changeText = '#' + githubId[1]
      } else if (/^[0-9a-f]{40}$/.test(changeId)) {
        changeText = changeId.slice(0, 7)
      }
    } else if (changeId.length === 40) {
      changeText = changeId.slice(0, 7)
    }
    return (
      <small>
        <a href={change.url}>
          {changeText !== '' ? (
            <abbr title={changeTitle}>{changeText}</abbr>) : changeTitle}
        </a>
      </small>)
  }

  renderProgressBar (change) {
    let jobPercent = (100 / change.jobs.length).toFixed(2)
    return (
      <div className='progress zuul-change-total-result'>
        {change.jobs.map((job, idx) => {
          let result = this.jobStrResult(job)
          if (result !== 'queued') {
            let className = ''
            switch (result) {
              case 'success':
                className = ' progress-bar-success'
                break
              case 'lost':
              case 'failure':
                className = ' progress-bar-danger'
                break
              case 'unstable':
              case 'retry_limit':
              case 'post_failure':
              case 'node_failure':
                className = ' progress-bar-warning'
                break
              case 'paused':
              case 'skipped':
                className = ' progress-bar-info'
                break
              default:
                break
            }
            return <div className={'progress-bar' + className}
              key={idx}
              title={job.name}
              style={{width: jobPercent + '%'}}/>
          } else {
            return ''
          }
        })}
      </div>
    )
  }

  renderTimer (change) {
    let remainingTime
    if (change.remaining_time === null) {
      remainingTime = 'unknown'
    } else {
      remainingTime = this.time(change.remaining_time)
    }
    return (
      <React.Fragment>
        <small title='Remaining Time' className='time'>
          {remainingTime}
        </small>
        <br />
        <small title='Elapsed Time' className='time'>
          {this.enqueueTime(change.enqueue_time)}
        </small>
      </React.Fragment>
    )
  }

  renderJobProgressBar (elapsedTime, remainingTime) {
    let progressPercent = 100 * (elapsedTime / (elapsedTime +
                                                remainingTime))
    // Show animation in preparation phase
    let className
    let progressWidth = progressPercent
    let title = ''
    let remaining = remainingTime
    if (Number.isNaN(progressPercent)) {
      progressWidth = 100
      progressPercent = 0
      className = 'progress-bar-striped progress-bar-animated'
    }
    if (remaining !== null) {
      title = 'Estimated time remaining: ' + moment.duration(remaining).format({
        template: 'd [days] h [hours] m [minutes] s [seconds]',
        largest: 2,
        minValue: 30,
      })
    }

    return (
      <div className='progress zuul-job-result'
        title={title}>
        <div className={'progress-bar ' + className}
          role='progressbar'
          aria-valuenow={progressPercent}
          aria-valuemin={0}
          aria-valuemax={100}
          style={{'width': progressWidth + '%'}}
        />
      </div>
    )
  }

  renderJobStatusLabel (result) {
    let className
    switch (result) {
      case 'success':
        className = 'label-success'
        break
      case 'failure':
        className = 'label-danger'
        break
      case 'unstable':
      case 'retry_limit':
      case 'post_failure':
      case 'node_failure':
        className = 'label-warning'
        break
      case 'paused':
      case 'skipped':
        className = 'label-info'
        break
      // 'in progress' 'queued' 'lost' 'aborted' 'waiting' ...
      default:
        className = 'label-default'
    }

    return (
      <span className={'zuul-job-result label ' + className}>{result}</span>
    )
  }

  renderJob (job) {
    const { tenant } = this.props
    let job_name = job.name
    if (job.tries > 1) {
      job_name = job_name + ' (' + job.tries + '. attempt)'
    }
    let name = ''
    if (job.result !== null) {
      name = <a className='zuul-job-name' href={job.report_url}>{job_name}</a>
    } else if (job.url !== null) {
      let url = job.url
      if (job.url.match('stream/')) {
        const to = (
          tenant.linkPrefix + '/' + job.url
        )
        name = <Link className='zuul-job-name' to={to}>{job_name}</Link>
      } else {
        name = <a className='zuul-job-name' href={url}>{job_name}</a>
      }
    } else {
      name = <span className='zuul-job-name'>{job_name}</span>
    }
    let resultBar
    let result = this.jobStrResult(job)
    if (result === 'in progress') {
      resultBar = this.renderJobProgressBar(
        job.elapsed_time, job.remaining_time)
    } else {
      resultBar = this.renderJobStatusLabel(result)
    }

    return (
      <span>
        {name}
        {resultBar}
        {job.voting === false ? (
          <small className='zuul-non-voting-desc'> (non-voting)</small>) : ''}
        <div style={{clear: 'both'}} />
      </span>)
  }

  renderJobList (jobs) {
    return (
      <ul className='list-group zuul-patchset-body'>
        {jobs.map((job, idx) => (
          <li key={idx} className='list-group-item zuul-change-job'>
            {this.renderJob(job)}
          </li>
        ))}
      </ul>)
  }

  render () {
    const { expanded } = this.state
    const { change, globalExpanded, user, tenant, pipeline } = this.props
    let expand = globalExpanded
    if (this.clicked) {
      expand = expanded
    }
    const header = (
      <div className='panel panel-default zuul-change'>
        <div>{ this.renderDequeueModal() }</div>
        <div>{ this.renderPromoteModal() }</div>
        <div className='panel-heading zuul-patchset-header'
          onClick={this.onClick}>
          <div className='row'>
            <div className='col-xs-8'>
              <div className='row'>
                {(user.isAdmin && user.scope.indexOf(tenant.name) !== -1) ?
                 (<div className='col-xs-1 my-auto text-left'>
                    {this.renderDequeueButton()}
                  </div>) :
                 ''}
                 {(user.isAdmin && user.scope.indexOf(tenant.name) !== -1 && pipeline.manager === 'dependent') ?
                  (<div className='col-xs-1 my-auto text-left'>
                     {this.renderPromoteButton()}
                   </div>) :
                  ''}
                <div className='col-xs-8'>
                  <span className='change_project'>{change.project}</span>
                </div>
              </div>
              <div className='row'>
                <div className='col-xs-2'>
                  {this.renderChangeLink(change)}
                </div>
                <div className='col-xs-8'>
                  {this.renderProgressBar(change)}
                </div>
              </div>
            </div>
            {change.live === true ? (
                <div className='col-xs-4 text-right'>
                  {this.renderTimer(change)}
              </div>
            ) : ''}
          </div>
        </div>
        {expand ? this.renderJobList(change.jobs) : ''}
      </div>
    )
    return (
      <React.Fragment>
        {header}
      </React.Fragment>
    )
  }
}

export default connect(state => ({
    tenant: state.tenant,
    user: state.user,
}))(ChangePanel)
