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

import * as moment from 'moment'
import 'moment-duration-format'
import * as React from 'react'
import ReAnsi from '@softwarefactory-project/re-ansi'
import PropTypes from 'prop-types'
import ReactJson from 'react-json-view'
import {
  Icon,
  ListView,
  Row,
  Col,
} from 'patternfly-react'

import {
  Chip,
  DataList,
  DataListItem,
  DataListItemRow,
  DataListCell,
  DataListItemCells,
  DataListToggle,
  DataListContent,
  Label,
  Modal,
  Popover
} from '@patternfly/react-core'

import {
  ContainerNodeIcon,
  InfoCircleIcon,
  SearchPlusIcon,
} from '@patternfly/react-icons'

import {
  hasInterestingKeys,
  findLoopLabel,
  shouldIncludeKey,
  makeTaskPath,
  taskPathMatches,
} from '../../actions/build'

const INTERESTING_KEYS = ['msg', 'cmd', 'stdout', 'stderr']


class TaskOutput extends React.Component {
  static propTypes = {
    data: PropTypes.object,
    include: PropTypes.array,
  }

  renderResults(value) {
    const interesting_results = []

    // This was written to assume "value" is an array of
    // key/value mappings to output.  This seems to be a
    // good assumption for the most part, but "package:" for
    // whatever reason outputs a result that is just an array of
    // strings with what packages were installed.  So, if we
    // see an array of strings as the value, we just swizzle
    // that into a key/value so it displays usefully.
    const isAllStrings = value.every(i => typeof i === "string")
    if (isAllStrings) {
      value = [ {output: [...value]} ]
    }

    value.forEach((result, idx) => {
      const keys = Object.entries(result).filter(
        ([key, value]) => shouldIncludeKey(
          key, value, true, this.props.include))
      if (keys.length) {
        interesting_results.push(idx)
      }
    })

    return (
      <div key='results'>
        {interesting_results.length>0 &&
         <React.Fragment>
           <h5 key='results-header'>results</h5>
           {interesting_results.map((idx) => (
             <div className='zuul-console-task-result' key={idx}>
               <h4 key={idx}>{idx}: {findLoopLabel(value[idx])}</h4>
               {Object.entries(value[idx]).map(([key, value]) => (
                 this.renderData(key, value, true)
               ))}
             </div>
           ))}
         </React.Fragment>
        }
      </div>
    )
  }

  renderData(key, value, ignore_underscore) {
    let ret
    if (!shouldIncludeKey(key, value, ignore_underscore, this.props.include)) {
      return (<React.Fragment key={key}/>)
    }
    if (value === null) {
      ret = (
        <pre>
          null
        </pre>
      )
    } else if (typeof(value) === 'string') {
      ret = (
        <pre>
          <ReAnsi log={value} />
        </pre>
      )
    } else if (typeof(value) === 'object') {
      ret = (
        <pre>
          <ReactJson
            src={value}
            name={null}
            sortKeys={true}
            enableClipboard={false}
            displayDataTypes={false}/>
        </pre>
      )
    } else {
      ret = (
        <pre>
          {value.toString()}
        </pre>
      )
    }

    return (
      <div key={key}>
        {ret && <h5>{key}</h5>}
        {ret && ret}
      </div>
    )
  }

  render () {
    const { data } = this.props

    return (
      <React.Fragment>
        {Object.entries(data).map(([key, value]) => (
          key==='results'?this.renderResults(value):this.renderData(key, value)
        ))}
      </React.Fragment>
    )
  }
}

class HostTask extends React.Component {
  static propTypes = {
    hostname: PropTypes.string,
    task: PropTypes.object,
    host: PropTypes.object,
    errorIds: PropTypes.object,
    taskPath: PropTypes.array,
    displayPath: PropTypes.array,
  }

  state = {
    showModal: false,
    failed: false,
    changed: false,
    skipped: false,
    ok: false
  }

  open = () => {
    this.setState({showModal: true})
  }

  close = () => {
    this.setState({showModal: false})
  }

  constructor (props) {
    super(props)

    const { host, taskPath, displayPath } = this.props

    if (host.failed) {
      this.state.failed = true
    } else if (host.changed) {
      this.state.changed = true
    } else if (host.skipped) {
      this.state.skipped = true
    } else {
      this.state.ok = true
    }

    if (taskPathMatches(taskPath, displayPath))
      this.state.showModal = true
  }

  render () {
    const { hostname, task, host, taskPath, errorIds } = this.props

    const ai = []

    let name = task.task.name
    if (!name) {
      name = host.action
    }
    if (task.role) {
      name = task.role.name + ': ' + name
    }

    ai.push(
      <DataListCell width={5}>{name}</DataListCell>
    )

    ai.push(
      <DataListCell isIcon={true} onClick={this.open}><SearchPlusIcon /></DataListCell>
    )

    if (this.state.failed) {
      ai.push(
        <DataListCell>
          <Label color="red" onClick={this.open}>FAILED</Label>
        </DataListCell>)
    } else if (this.state.changed) {
      ai.push(
        <DataListCell>
          <Label color="orange" onClick={this.open}>CHANGED</Label>
        </DataListCell>)
    } else if (this.state.skipped) {
      ai.push(
        <DataListCell>
          <Label color="grey" onClick={this.open}>SKIPPED</Label>
        </DataListCell>)
    } else if (this.state.ok) {
      ai.push(
        <DataListCell>
          <Label color="green" onClick={this.open}>OK</Label>
        </DataListCell>)
    }
    ai.push(
      <DataListCell>
        <Chip isReadOnly={true}><ContainerNodeIcon />&nbsp;{hostname}</Chip>
      </DataListCell>
    )

    let duration = moment.duration(
      moment(task.task.duration.end).diff(task.task.duration.start)
    ).format({
      template: 'h [hr] m [min] s [sec]',
      largest: 2,
      minValue: 1,
    })

    ai.push(
      <DataListCell key="task-duration">
        <span className="task-duration">{duration}</span>
      </DataListCell>
    )

    const expand = errorIds.has(task.task.id)

    const has_interesting_keys = hasInterestingKeys(this.props.host, INTERESTING_KEYS)
    let lc = undefined
    if (!has_interesting_keys) {
      lc = []
    }
    return (
      <>
        <DataListItemCells dataListCells={ ai } />
        <Modal
          title={hostname}
          isOpen={this.state.showModal}
          onClose={this.close}
          dialogClassName="zuul-console-task-detail">
          <span className="zuul-console-modal-header-link">
            <a href={'#'+makeTaskPath(taskPath)}>
              <Icon type="fa" name="link" title="Permalink" />
            </a>
          </span>
          <TaskOutput data={host}/>
        </Modal>
      </>
    )
  }
}

class PlayBook extends React.Component {
  static propTypes = {
    playbook: PropTypes.object,
    errorIds: PropTypes.object,
    taskPath: PropTypes.array,
    displayPath: PropTypes.array,
  }

  constructor(props) {
    super(props);
    this.state = {
      expanded: false,
      playsExpanded: []
    }
  }

  render () {
    const { playbook, errorIds, taskPath, displayPath } = this.props

    const expandAll = (playbook.phase === 'run')
    const expand = (expandAll ||
                    errorIds.has(playbook.phase + playbook.index) ||
                    taskPathMatches(taskPath, displayPath))

    const togglePlays = id => {
      const index = this.state.playsExpanded.indexOf(id);
      const newExpanded =
            index >= 0 ? [...this.state.playsExpanded.slice(0, index), ...this.state.playsExpanded.slice(index + 1, this.state.playsExpanded.length)] : [...this.state.playsExpanded, id];
      this.setState({playsExpanded: newExpanded})
      console.log(this.state)
    };

    const makePlayId = (play, idx) => play.play.name + "-" + idx

    // This is the header for each playbook
    var dataListCells = []
    dataListCells.push(<DataListCell width={1}><strong>{playbook.phase[0].toUpperCase() + playbook.phase.slice(1)} playbook</strong></DataListCell>)
    dataListCells.push(<DataListCell width={5}>{playbook.playbook}</DataListCell>)
    if (playbook.trusted) {
      dataListCells.push(
        <DataListCell>
          <Popover bodyContent={<div>This playbook runs in a trusted execution context, which permits executing code on the Zuul executor and allows access to all Ansible features.</div>}>
          <Label color="blue" icon={<InfoCircleIcon />}>Trusted</Label></Popover></DataListCell>)
    } else {
      dataListCells.push(
        <DataListCell>
          <Popover bodyContent={<div>This playbook runs in an untrusted execution context.</div>}>
          <Label color="grey" icon={<InfoCircleIcon />}>Untrusted</Label></Popover></DataListCell>)
    }
      
    return (
      <DataListItem isExpanded={this.state.expanded}>

        <DataListItemRow>
          <DataListToggle
            onClick={() => this.setState({expanded: !this.state.expanded})}
            isExpanded={this.state.expanded}/>
          <DataListItemCells
            dataListCells={dataListCells} />
        </DataListItemRow>

        <DataListContent isHidden={!this.state.expanded}>

          {playbook.plays.map((play, idx) => (
            <DataList isCompact={true}>
              <DataListItem isExpanded={this.state.playsExpanded.includes(makePlayId(play, idx))}>
                <DataListItemRow>
                  <DataListToggle
                    onClick={() => togglePlays(makePlayId(play, idx))}
                    isExpanded={this.state.playsExpanded.includes(makePlayId(play, idx))}
                    id={makePlayId(play, idx)}/>
                  <DataListItemCells dataListCells={[
                                       <DataListCell>Play: {play.play.name}</DataListCell>
                                     ]}
                  />
                </DataListItemRow>
                <DataListContent
                  isHidden={!this.state.playsExpanded.includes(makePlayId(play, idx))}>

                  <DataList isCompact={true}>
                    {play.tasks.map((task, idx2) => (
                      Object.entries(task.hosts).map(([hostname, host]) => (
                        <DataListItem>
                          <DataListItemRow>
                            <HostTask hostname={hostname}
                                      taskPath={taskPath.concat([
                                        idx.toString(), idx2.toString(), hostname])}
                                      displayPath={displayPath} task={task} host={host}
                                      errorIds={errorIds}/>
                          </DataListItemRow>
                        </DataListItem>
                      ))))}
                  </DataList>

                </DataListContent>
              </DataListItem>
            </DataList>
          ))}

        </DataListContent>
      </DataListItem>
    )
  }
}


class Console extends React.Component {
  static propTypes = {
    errorIds: PropTypes.object,
    output: PropTypes.array,
    displayPath: PropTypes.array,
  }

  render () {
    const { errorIds, output, displayPath } = this.props

    return (
      <React.Fragment>
        <DataList key="playbooks">
          {output.map((playbook, idx) => (
            <PlayBook key={idx} playbook={playbook} taskPath={[idx.toString()]}
              displayPath={displayPath} errorIds={errorIds}/>))}
        </DataList>
      </React.Fragment>
    )
  }
}


export default Console
