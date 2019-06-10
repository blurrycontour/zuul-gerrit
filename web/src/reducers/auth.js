import update from 'immutability-helper'

import {
  USER_EXPIRED,
  USER_FOUND,
  SILENT_RENEW_ERROR,
  SESSION_TERMINATED,
  LOADING_USER,
  USER_SIGNED_OUT
} from 'redux-oidc'
import {
  LOADING_USER_AUTHORIZATIONS,
  USER_AUTHORIZATIONS_LOADED
} from '../actions/auth'

const initialState = {
  user: null,
  isLoadingUser: false,
  // TODO: set to null, so we know if "adminTenants" needs to be fetched
  adminTenants: []
}

export default function reducer(state = initialState, action) {
  switch (action.type) {
    case USER_EXPIRED:
        return { user: null, isLoadingUser: false, adminTenants: [] }
    case SILENT_RENEW_ERROR:
        return { user: null, isLoadingUser: false, adminTenants: [] }
    case SESSION_TERMINATED:
    case USER_SIGNED_OUT:
        return { user: null, isLoadingUser: false, adminTenants: [] }
    case USER_FOUND:
        return { user: action.payload, isLoadingUser: false, adminTenants: [] }
    case LOADING_USER:
        return { user: null, isLoadingUser: true, adminTenants: [] }
    case LOADING_USER_AUTHORIZATIONS:
        return update(state, { isLoadingUser: {$set: true}, adminTenants: {$set: []} })
    case USER_AUTHORIZATIONS_LOADED:
        console.log(action.adminTenants)
        return update(state, { isLoadingUser: {$set: false}, adminTenants: {$set: action.adminTenants} })
    default:
        return state
  }
}
