import { createUserManager } from 'redux-oidc'
import userManagerConfig from './config'

let _userManager = null

if (userManagerConfig !== null) {
  _userManager = createUserManager(userManagerConfig)
}

const userManager = _userManager

export default userManager
