import { createUserManager } from 'redux-oidc'
import userManagerConfig from './config'

const userManager = createUserManager(userManagerConfig)

export default userManager
