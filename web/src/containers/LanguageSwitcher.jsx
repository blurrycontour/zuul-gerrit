// Copyright 2020 Red Hat, Inc
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

import PropTypes from 'prop-types'
import React from 'react'
import Select from 'react-select'
import { Icon } from 'patternfly-react'
import { connect } from 'react-redux'

import { supportedLocales, fallbackLocale } from '../locales/config'
import { setLocaleWithFallback } from '../actions/i18n'

class LanguageSelector extends React.Component {
  static propTypes = {
    dispatch: PropTypes.func,
  }

  state = {
    availableLanguages: Object.keys(supportedLocales).map(key => (
      {value: key, label: supportedLocales[key]}
    )),
    defaultLanguage: {value: fallbackLocale, label: supportedLocales[fallbackLocale]}
  }

  componentDidMount () {
    this.loadState()
  }

  loadState = () => {
    const { defaultLanguage } = this.state
    this.updateState(defaultLanguage)
  }

  handleChange = (language) => {
    this.updateState(language)
  }

  updateState = (language) => {
    this.setState(
      {currentValue: language}
    )
    let lg = language.value
    let lgAction = setLocaleWithFallback(lg)
    this.props.dispatch(lgAction)
  }

  render () {
    // from selectTz
    const textColor = '#d1d1d1'
    const containerStyles= {
      border: 'solid #2b2b2b',
      borderWidth: '0 0 0 1px',
      cursor: 'pointer',
      display: 'initial',
      fontSize: '11px',
      padding: '6px'
    }
    const iconStyles = {
      padding: '5px'
    }
    const customStyles = {
      container: () => ({
        display: 'inline-block',
      }),
      control: () => ({
        width: 'auto',
        display: 'flex'
      }),
      singleValue: () => ({
        color: textColor,
      }),
      input: (provided) => ({
        ...provided,
        color: textColor
      }),
      dropdownIndicator:(provided) => ({
        ...provided,
        padding: '3px'
      }),
      indicatorSeparator: () => {},
      menu: (provided) => ({
        ...provided,
        width: 'auto',
        right: '0',
        top: '22px',
      })
    }
    return (
      <div style={containerStyles}>
        <Icon style={iconStyles} type="fa" name="globe" />
        <Select
          styles={customStyles}
          value={this.state.currentValue}
          onChange={this.handleChange}
          options={this.state.availableLanguages}
          defaultValue={this.state.defaultLanguage} />
      </div>
    )
  }

}

export default connect(state => ({locale: state.i18n.locale}))(LanguageSelector)
