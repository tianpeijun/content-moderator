import axios from 'axios'

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// Request interceptor: attach Cognito Bearer token
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('cognito_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Response interceptor: redirect to login on 401 only
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // Only clear auth on explicit 401 responses, not on network/CORS errors
    if (error.response && error.response.status === 401) {
      localStorage.removeItem('cognito_token')
      localStorage.removeItem('cognito_user')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default apiClient
