<template>
  <div style="display: flex; justify-content: center; align-items: center; min-height: 100vh; background: #f0f2f5">
    <a-card style="width: 400px" title="内容审核系统 — 登录">
      <!-- Normal login form -->
      <a-form v-if="!showNewPassword" layout="vertical">
        <a-form-item label="邮箱">
          <a-input v-model:value="username" placeholder="请输入邮箱" size="large" @pressEnter="handleLogin" />
        </a-form-item>
        <a-form-item label="密码">
          <a-input-password v-model:value="password" placeholder="请输入密码" size="large" @pressEnter="handleLogin" />
        </a-form-item>
        <a-form-item>
          <a-button type="primary" :loading="loading" block size="large" @click="handleLogin">
            登录
          </a-button>
        </a-form-item>
      </a-form>

      <!-- New password form (first login) -->
      <a-form v-else layout="vertical">
        <a-alert message="首次登录，请设置新密码" type="info" show-icon style="margin-bottom: 16px" />
        <a-form-item label="新密码">
          <a-input-password v-model:value="newPassword" placeholder="请输入新密码（至少8位，含大写字母和数字）" size="large" @pressEnter="handleNewPassword" />
        </a-form-item>
        <a-form-item label="确认密码">
          <a-input-password v-model:value="confirmPassword" placeholder="请再次输入新密码" size="large" @pressEnter="handleNewPassword" />
        </a-form-item>
        <a-form-item>
          <a-button type="primary" :loading="loading" block size="large" @click="handleNewPassword">
            设置密码并登录
          </a-button>
        </a-form-item>
      </a-form>

      <a-alert v-if="errorMsg" :message="errorMsg" type="error" show-icon style="margin-top: 12px" />
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import type { CognitoUser } from 'amazon-cognito-identity-js'
import { login, completeNewPassword } from '../services/cognito'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const username = ref('')
const password = ref('')
const loading = ref(false)
const errorMsg = ref('')

// New password challenge state
const showNewPassword = ref(false)
const newPassword = ref('')
const confirmPassword = ref('')
let pendingCognitoUser: CognitoUser | null = null

async function handleLogin() {
  if (!username.value || !password.value) {
    errorMsg.value = '请输入邮箱和密码'
    return
  }
  loading.value = true
  errorMsg.value = ''

  try {
    const result = await login(username.value, password.value)

    if (result.success && result.session) {
      const token = result.session.getIdToken().getJwtToken()
      authStore.setAuth(token, username.value)
      message.success('登录成功')
      router.push('/')
    } else if (result.newPasswordRequired && result.cognitoUser) {
      showNewPassword.value = true
      pendingCognitoUser = result.cognitoUser
    } else {
      errorMsg.value = result.error || '登录失败'
    }
  } catch (e: any) {
    errorMsg.value = e.message || '登录异常'
  }

  loading.value = false
}

async function handleNewPassword() {
  if (!newPassword.value || !confirmPassword.value) {
    errorMsg.value = '请输入新密码'
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    errorMsg.value = '两次输入的密码不一致'
    return
  }
  if (!pendingCognitoUser) {
    errorMsg.value = '会话已过期，请重新登录'
    showNewPassword.value = false
    return
  }

  loading.value = true
  errorMsg.value = ''

  const result = await completeNewPassword(pendingCognitoUser, newPassword.value)

  if (result.success && result.session) {
    const token = result.session.getIdToken().getJwtToken()
    authStore.setAuth(token, username.value)
    message.success('密码设置成功，已登录')
    router.push('/')
  } else {
    errorMsg.value = result.error || '密码设置失败'
  }

  loading.value = false
}
</script>
