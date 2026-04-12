/**
 * Cognito authentication service using amazon-cognito-identity-js.
 */
import {
  CognitoUserPool,
  CognitoUser,
  AuthenticationDetails,
  CognitoUserSession,
} from 'amazon-cognito-identity-js'

const POOL_DATA = {
  UserPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID || '',
  ClientId: import.meta.env.VITE_COGNITO_APP_CLIENT_ID || '',
}

const userPool = new CognitoUserPool(POOL_DATA)

export interface LoginResult {
  success: boolean
  newPasswordRequired?: boolean
  session?: CognitoUserSession
  error?: string
  cognitoUser?: CognitoUser
}

/**
 * Authenticate with username + password.
 * Handles NEW_PASSWORD_REQUIRED challenge.
 */
export function login(username: string, password: string): Promise<LoginResult> {
  return new Promise((resolve) => {
    const user = new CognitoUser({ Username: username, Pool: userPool })
    const authDetails = new AuthenticationDetails({
      Username: username,
      Password: password,
    })

    user.authenticateUser(authDetails, {
      onSuccess(session: CognitoUserSession) {
        resolve({ success: true, session })
      },
      onFailure(err: Error) {
        resolve({ success: false, error: err.message || 'Login failed' })
      },
      newPasswordRequired() {
        resolve({ success: false, newPasswordRequired: true, cognitoUser: user })
      },
    })
  })
}

/**
 * Complete NEW_PASSWORD_REQUIRED challenge.
 */
export function completeNewPassword(
  cognitoUser: CognitoUser,
  newPassword: string
): Promise<LoginResult> {
  return new Promise((resolve) => {
    cognitoUser.completeNewPasswordChallenge(newPassword, {}, {
      onSuccess(session: CognitoUserSession) {
        resolve({ success: true, session })
      },
      onFailure(err: Error) {
        resolve({ success: false, error: err.message || 'Password change failed' })
      },
    })
  })
}

/**
 * Get the current session's ID token (JWT string).
 */
export function getIdToken(): string | null {
  const user = userPool.getCurrentUser()
  if (!user) return null
  let token: string | null = null
  user.getSession((err: Error | null, session: CognitoUserSession | null) => {
    if (!err && session?.isValid()) {
      token = session.getIdToken().getJwtToken()
    }
  })
  return token
}

/**
 * Sign out the current user.
 */
export function signOut(): void {
  const user = userPool.getCurrentUser()
  if (user) user.signOut()
}
