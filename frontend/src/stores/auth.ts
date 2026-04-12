import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('cognito_token'))
  const user = ref<string | null>(localStorage.getItem('cognito_user'))

  const isAuthenticated = computed(() => !!token.value)

  function setAuth(newToken: string, username: string) {
    token.value = newToken
    user.value = username
    localStorage.setItem('cognito_token', newToken)
    localStorage.setItem('cognito_user', username)
  }

  function clearAuth() {
    token.value = null
    user.value = null
    localStorage.removeItem('cognito_token')
    localStorage.removeItem('cognito_user')
  }

  return { token, user, isAuthenticated, setAuth, clearAuth }
})
