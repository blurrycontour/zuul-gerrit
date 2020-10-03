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

import PropTypes from 'prop-types'
import React from 'react'
import moment from 'moment-timezone'
import { connect } from 'react-redux'
import { Select, SelectOption, SelectVariant } from '@patternfly/react-core'

class Timezone extends React.Component {

  static propTypes = {
    selected: PropTypes.string,
    onSelect: PropTypes.func
  }

  constructor(props) {
    super(props)

    const defaultSelected = this.props.selected

    this.state = {
      options: moment.tz.names().map(item => ({value: item, label: item})),
      isOpen: false,
      hasOnCreateOption: false,
      selected: null,
    }

    this.onToggle = isOpen => {
      this.setState({
        isOpen
      })
    }

    this.onSelect = (event, selection, isPlaceholder) => {
      if (isPlaceholder) this.clearSelection()
      else {
         this.setState({
         selected: selection,
         isOpen: false
        })
        this.props.onSelect(selection)
      }
    }

    this.clearSelection = () => {
      this.setState({
          isOpen: false,
          selected: null,
      })
      this.props.onSelect(defaultSelected)
    }

    this.getSelectOptions = options => {
      return options.map((option, index) => (
        <SelectOption
          key={index}
          value={option.value}
          {...(option.description && { description: option.description })}
        />
      ))
    }

    this.customFilter = e => {
      let input
      try {
        input = new RegExp(e.target.value, 'i')
      } catch (err) {
        return ''
      }
      return this.getSelectOptions(e.target.value !== ''
          ? this.state.options.filter(item => input.test(item.value))
          : this.state.options)
    }

  }

  render() {
    const { isOpen, options, selected } = this.state
    const titleId = 'select-timezone-typeahead'
    const label = 'Timezones'
    return (
      <div>
        <Select
          variant={SelectVariant.typeahead}
          typeAheadAriaLabel={label}
          aria-labelledby={titleId}
          isOpen={isOpen}
          menuAppendTo='parent'
          onClear={this.clearSelection}
          onFilter={this.customFilter}
          onSelect={this.onSelect}
          onToggle={this.onToggle}
          placeholderText={this.props.selected}
          selections={selected}
          maxHeight="200px"
        >
          <SelectOption key={-1} value="UTC" description="This is the default timezone." />
          {this.getSelectOptions(options)}
        </Select>
      </div>
    )
  }
}


export default connect()(Timezone)
