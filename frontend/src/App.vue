<template>
  <!-- Login page: no sidebar layout -->
  <router-view v-if="isLoginPage" />

  <!-- Authenticated layout with sidebar -->
  <a-layout v-else style="min-height: 100vh">
    <a-layout-sider v-model:collapsed="collapsed" collapsible>
      <div style="height: 32px; margin: 16px; color: #fff; text-align: center; font-size: 16px; line-height: 32px;">
        内容审核系统
      </div>
      <a-menu theme="dark" mode="inline" :selectedKeys="selectedKeys" @click="onMenuClick">
        <a-menu-item key="/rules">
          <template #icon><UnorderedListOutlined /></template>
          <span>规则管理</span>
        </a-menu-item>
        <a-menu-item key="/prompt">
          <template #icon><FileTextOutlined /></template>
          <span>提示词预览与测试</span>
        </a-menu-item>
        <a-menu-item key="/logs">
          <template #icon><FileSearchOutlined /></template>
          <span>审核日志</span>
        </a-menu-item>
        <a-menu-item key="/test">
          <template #icon><ExperimentOutlined /></template>
          <span>批量测试</span>
        </a-menu-item>
        <a-menu-item key="/test-records">
          <template #icon><HistoryOutlined /></template>
          <span>测试记录</span>
        </a-menu-item>
        <a-menu-item key="/model-config">
          <template #icon><SettingOutlined /></template>
          <span>模型配置</span>
        </a-menu-item>
        <a-menu-item key="/stats">
          <template #icon><BarChartOutlined /></template>
          <span>数据统计</span>
        </a-menu-item>
        <a-menu-item key="/labels">
          <template #icon><TagsOutlined /></template>
          <span>标签管理</span>
        </a-menu-item>
      </a-menu>
    </a-layout-sider>
    <a-layout>
      <a-layout-header style="background: #fff; padding: 0 16px; display: flex; align-items: center; justify-content: space-between;">
        <span style="font-size: 16px; font-weight: 500;">{{ currentTitle }}</span>
        <a-space>
          <span style="color: #666; font-size: 13px">{{ authStore.user }}</span>
          <a-button size="small" @click="handleLogout">退出登录</a-button>
        </a-space>
      </a-layout-header>
      <a-layout-content style="margin: 16px;">
        <div style="padding: 24px; background: #fff; min-height: 360px; border-radius: 8px;">
          <router-view />
        </div>
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  UnorderedListOutlined,
  FileTextOutlined,
  FileSearchOutlined,
  ExperimentOutlined,
  HistoryOutlined,
  SettingOutlined,
  BarChartOutlined,
  TagsOutlined,
} from '@ant-design/icons-vue'
import { useAuthStore } from './stores/auth'
import { signOut } from './services/cognito'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const collapsed = ref(false)

const isLoginPage = computed(() => route.name === 'Login')
const selectedKeys = computed(() => [route.path])
const currentTitle = computed(() => (route.meta?.title as string) || '')

function onMenuClick({ key }: { key: string }) {
  router.push(key)
}

function handleLogout() {
  signOut()
  authStore.clearAuth()
  router.push('/login')
}
</script>
