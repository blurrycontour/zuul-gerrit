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
import { Badge } from '@patternfly/react-core'
import { Card, CardHeader, CardBody } from '@patternfly/react-core'
import { Divider } from '@patternfly/react-core'
import { ExpandableSection } from '@patternfly/react-core'
import { PageSection } from '@patternfly/react-core'
import { ToggleGroup, ToggleGroupItem } from '@patternfly/react-core'

function updateSelection (event) {
  const lines = window.location.hash.substring(1).split('-').map(Number)
  const lineClicked = Number(event.currentTarget.innerText)
  if (!event.shiftKey || lines.length === 0) {
    // First line clicked
    lines[0] = [lineClicked]
    lines.splice(1, 1)
  } else {
    // Second line shift-clicked
    const distances = lines.map((pos) => (Math.abs(lineClicked - pos)))
    // Adjust the range based on the edge distance
    if (distances[0] < distances[1]) {
      lines[0] = lineClicked
    } else {
      lines[1] = lineClicked
    }
  }
  window.location.hash = '#' + lines.sort().join('-')
}


class LogFile extends React.Component {
  static propTypes = {
    build: PropTypes.object,
    item: PropTypes.object,
    tenant: PropTypes.object,
    data: PropTypes.array,
  }

    constructor(props) {
        super(props)
        this.state = {
            redirect: null,
            severity: '',
            isExpanded: false
        };
        this.handleItemClick = (isSelected, event) => {
            let id = event.currentTarget.id
            if (id === 'all') {
                id = '';
            }
            this.setState({ severity: id })
        };
        this.onToggle = (isExpanded) => {
            this.setState({
                isExpanded
            })
        }
    }

  render () {
    const { build, data } = this.props
    const { severity, isExpanded } = this.state;
    const fileName = window.location.pathname.substr(window.location.pathname.lastIndexOf('/') + 1);
    return (
        <React.Fragment>
            <Card>
                <CardHeader>
                    {fileName}
                </CardHeader>
                <CardBody>
                    <Badge isRead>Build {build.uuid}</Badge>
                </CardBody>
            </Card>
            <ExpandableSection
                toggleText={isExpanded ? 'Hide Filters' : 'Show Filters'}
                onToggle={this.onToggle} isExpanded={isExpanded}>
                <ToggleGroup aria-label='Log line severity filter'>
                    <ToggleGroupItem
                        buttonId='all' isSelected={severity === ''}
                        onChange={this.handleItemClick}>
                        All
                    </ToggleGroupItem>
                    <ToggleGroupItem
                        buttonId='1' isSelected={severity === '1'}
                        onChange={this.handleItemClick}>
                        Debug
                    </ToggleGroupItem>
                    <ToggleGroupItem
                        buttonId='2' isSelected={severity === '2'}
                        onChange={this.handleItemClick}>
                        Info
                    </ToggleGroupItem>
                    <ToggleGroupItem
                        buttonId='3' isSelected={severity === '3'}
                        onChange={this.handleItemClick}>
                        Warning
                    </ToggleGroupItem>
                    <ToggleGroupItem
                        buttonId='4' isSelected={severity === '4'}
                        onChange={this.handleItemClick}>
                        Error
                    </ToggleGroupItem>
                    <ToggleGroupItem
                        buttonId='5' isSelected={severity === '5'}
                        onChange={this.handleItemClick}>
                        Trace
                    </ToggleGroupItem>
                    <ToggleGroupItem
                        buttonId='6' isSelected={severity === '6'}
                        onChange={this.handleItemClick}>
                        Audit
                    </ToggleGroupItem>
                    <ToggleGroupItem
                        buttonId='7' isSelected={severity === '7'}
                        onChange={this.handleItemClick}>
                        Critical
                    </ToggleGroupItem>
                </ToggleGroup>
            </ExpandableSection>
            <Divider/>
            <PageSection>
                <pre className="zuul-log-output">
                    <table>
                        <tbody>
                            {data.map((line) => (
                                ((!severity || (line.severity >= severity)) &&
                                 <tr key={line.index} className={'ln-' + line.index}>
                                     <td className="line-number" onClick={updateSelection}>
                                         {line.index}
                                     </td>
                                     <td>
                                         <span className={`log-message zuul-log-sev-${line.severity || 0}`}>
                                             {line.text+'\n'}
                                         </span>
                                     </td>
                                 </tr>
                                )))}
                        </tbody>
                    </table>
                </pre>
            </PageSection>
        </React.Fragment>
    )
  }
}


export default connect(state => ({tenant: state.tenant}))(LogFile)
