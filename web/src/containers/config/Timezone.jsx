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

import React from 'react';
import moment from 'moment-timezone'
import { connect } from 'react-redux'
import { Select, SelectOption, SelectVariant } from '@patternfly/react-core';

class Timezone extends React.Component {
  constructor(props) {
    super(props);

    this.state = {
      options: moment.tz.names().map(item => ({value: item, label: item})),
      isOpen: false,
      selected: null,
      hasOnCreateOption: false
    };

    this.onToggle = isOpen => {
      this.setState({
        isOpen
      });
    };

    this.onSelect = (event, selection, isPlaceholder) => {
      if (isPlaceholder) this.clearSelection();
      else {
        this.setState({
          selected: selection,
          isOpen: false
        });
        this.props.onSelect(selection);
        console.log('selected:', selection);
      }
    };

    this.clearSelection = () => {
      this.setState({
        selected: null,
        isOpen: false
      });
    };

    this.getSelectOptions = (options) => {
      return options.map((option, index) => (
        <SelectOption
          key={index}
          value={option.value}
          {...(option.description && { description: option.description })}
        />
      ))
    }

    this.customFilter = e => {
      let input;
      try {
        input = new RegExp(e.target.value, 'i');
      } catch (err) {}
      return e.target.value !== '' ?
        this.getSelectOptions(this.state.options.filter(item => input.test(item.value))) :
        this.getSelectOptions(this.state.options);
    };

  }

  render() {
    const { isOpen, options, selected } = this.state;
    const { value } = this.props
    const titleId = 'select-timezone-typeahead';
    return (
      <div>
        <Select
          variant={SelectVariant.typeahead}
          typeAheadAriaLabel="Select a local"
          onToggle={this.onToggle}
          onSelect={this.onSelect}
          onClear={this.clearSelection}
          onFilter={this.customFilter}
          selections={selected || value }
          isOpen={isOpen}
          aria-labelledby={titleId}
          placeholderText="Select a local"
          menuAppendTo="parent"
        >
          {this.getSelectOptions(options)}
        </Select>
      </div>
    );
  }
}


export default connect()(Timezone)
