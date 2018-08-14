import React from 'react'
import ReactDOM from 'react-dom'
import { BrowserRouter as Router } from 'react-router-dom'
import { Provider } from 'react-redux'
import { store } from './reducers'
import App from './App'

it('renders without crashing', () => {
  const div = document.createElement('div')
  ReactDOM.render(<Provider store={store}><Router><App /></Router></Provider>,
    div)
  ReactDOM.unmountComponentAtNode(div)
})
