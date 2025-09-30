import axios from 'axios'
import type { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import router from '@/router'

// API响应接口
export interface ApiResponse<T = any> {
  success: boolean
  data: T
  message: string
  code?: number
  timestamp?: string
  request_id?: string
}

// 请求配置接口
export interface RequestConfig extends AxiosRequestConfig {
  skipAuth?: boolean
  skipErrorHandler?: boolean
  showLoading?: boolean
  loadingText?: string
}

// 创建axios实例
const createAxiosInstance = (): AxiosInstance => {
  const instance = axios.create({
    baseURL: import.meta.env.VITE_API_BASE_URL || '',
    timeout: 10000, // 减少超时时间到10秒
    headers: {
      'Content-Type': 'application/json'
    }
  })

  // 请求拦截器
  instance.interceptors.request.use(
    (config: any) => {
      const authStore = useAuthStore()
      const appStore = useAppStore()

      // 添加认证头（总是覆盖为最新Token；支持localStorage兜底，避免早期请求丢Token）
      if (!config.skipAuth) {
        const token = authStore.token || localStorage.getItem('auth-token')
        if (token) {
          config.headers = config.headers || {}
          config.headers.Authorization = `Bearer ${token}`
          console.log('🔐 已设置Authorization头:', {
            hasToken: !!token,
            tokenLength: token?.length || 0,
            tokenPrefix: token?.substring(0, 20) || 'None',
            authHeader: config.headers.Authorization?.substring(0, 30) || 'None'
          })
        } else {
          console.log('⚠️ 未设置Authorization头:', {
            skipAuth: config.skipAuth,
            hasToken: !!authStore.token,
            localStored: !!localStorage.getItem('auth-token'),
            url: config.url
          })
        }
      }

      // 添加请求ID
      config.headers['X-Request-ID'] = generateRequestId()

      // 添加语言头
      config.headers['Accept-Language'] = appStore.language

      // 显示加载状态
      if (config.showLoading) {
        appStore.setLoading(true, 0)
      }

      // 端点兼容守卫：阻止/修正误用的 /api/stocks/quote（缺少路径参数 {code}）
      try {
        const rawUrl = String(config.url || '')
        const pathOnly = rawUrl.split('?')[0].replace(/\/+$|^\s+|\s+$/g, '')
        if (pathOnly === '/api/stocks/quote' || pathOnly === '/api/stocks/quote/') {
          const code = (config.params && (config.params.code || (config as any).params?.stock_code)) ?? undefined
          if (code) {
            const codeStr = String(code)
            config.url = `/api/stocks/${codeStr}/quote`
            if (config.params) {
              delete (config.params as any).code
              delete (config.params as any).stock_code
            }
            console.warn('🔧 已自动重写遗留端点为 /api/stocks/{code}/quote', { code: codeStr })
          } else {
            console.error('❌ 误用端点: /api/stocks/quote 缺少 code。请改用 /api/stocks/{code}/quote', { stack: new Error().stack })
            return Promise.reject(new Error('前端误用端点：缺少 code，请改用 /api/stocks/{code}/quote'))
          }
        }
      } catch (e) {
        console.warn('端点兼容检查异常', e)
      }

      console.log(`🚀 API请求: ${config.method?.toUpperCase()} ${config.url}`, {
        baseURL: config.baseURL,
        fullURL: `${config.baseURL}${config.url}`,
        params: config.params,
        data: config.data,
        headers: config.headers,
        timeout: config.timeout
      })

      return config
    },
    (error) => {
      console.error('❌ 请求拦截器错误:', error)
      return Promise.reject(error)
    }
  )

  // 响应拦截器
  instance.interceptors.response.use(
    (response: AxiosResponse) => {
      const appStore = useAppStore()
      const config = response.config as RequestConfig

      // 隐藏加载状态
      if (config.showLoading) {
        appStore.setLoading(false)
      }

      console.log(`✅ API响应: ${response.status} ${response.config.url}`, response.data)

      // 检查业务状态码
      const data = response.data as ApiResponse
      if (data && typeof data === 'object' && 'success' in data) {
        if (!data.success && !config.skipErrorHandler) {
          handleBusinessError(data)
          return Promise.reject(new Error(data.message || '请求失败'))
        }
      }

      return response
    },
    async (error) => {
      const appStore = useAppStore()
      const authStore = useAuthStore()
      const config = error.config as RequestConfig

      // 隐藏加载状态
      if (config?.showLoading) {
        appStore.setLoading(false)
      }

      console.error(`❌ API错误: ${error.response?.status} ${error.config?.url}`, {
        error: error,
        message: error.message,
        code: error.code,
        response: error.response,
        request: error.request,
        config: error.config,
        stack: error.stack
      })

      // 处理HTTP状态码错误
      if (error.response) {
        const { status, data } = error.response

        switch (status) {
          case 401:
            // 如果是refresh请求本身失败，不要再次尝试刷新（避免无限循环）
            if (config?.url?.includes('/auth/refresh')) {
              console.error('❌ Refresh token请求失败，清除认证信息')
              authStore.clearAuthInfo()
              router.push('/login')
              ElMessage.error('登录已过期，请重新登录')
              break
            }

            // 未授权，尝试刷新token
            if (!config?.skipAuth && authStore.refreshToken) {
              try {
                console.log('🔄 401错误，尝试刷新token...')
                const success = await authStore.refreshAccessToken()
                if (success) {
                  console.log('✅ Token刷新成功，重试原请求')
                  // 重新发送原请求
                  return instance.request(config)
                } else {
                  console.log('❌ Token刷新失败')
                }
              } catch (refreshError) {
                console.error('❌ Token刷新异常:', refreshError)
              }
            }

            // 清除认证信息并跳转到登录页
            console.log('🧹 清除认证信息并跳转登录')
            authStore.clearAuthInfo()
            router.push('/login')
            ElMessage.error('登录已过期，请重新登录')
            break

          case 403:
            ElMessage.error('权限不足，无法访问该资源')
            break

          case 404:
            ElMessage.error('请求的资源不存在')
            break

          case 429:
            ElMessage.error('请求过于频繁，请稍后重试')
            break

          case 500:
            ElMessage.error('服务器内部错误，请稍后重试')
            break

          case 502:
          case 503:
          case 504:
            ElMessage.error('服务暂时不可用，请稍后重试')
            break

          default:
            if (!config?.skipErrorHandler) {
              const message = data?.message || error.message || '网络请求失败'
              ElMessage.error(message)
            }
        }
      } else if (error.code === 'ECONNABORTED') {
        console.error('🔍 [REQUEST] 请求超时错误:', {
          code: error.code,
          message: error.message,
          timeout: config?.timeout,
          url: config?.url
        })
        ElMessage.error('请求超时，请检查网络连接')
      } else if (error.message === 'Network Error') {
        console.error('🔍 [REQUEST] 网络连接错误:', {
          message: error.message,
          code: error.code,
          url: config?.url,
          baseURL: config?.baseURL
        })
        ElMessage.error('网络连接失败，请检查网络设置')
      } else if (error.message.includes('Failed to fetch')) {
        console.error('🔍 [REQUEST] Fetch失败错误:', {
          message: error.message,
          code: error.code,
          url: config?.url,
          baseURL: config?.baseURL
        })
        ElMessage.error('网络请求失败，请检查服务器连接')
      } else if (!config?.skipErrorHandler) {
        console.error('🔍 [REQUEST] 其他错误:', {
          message: error.message,
          code: error.code,
          name: error.name,
          url: config?.url
        })
        ElMessage.error(error.message || '未知错误')
      }

      return Promise.reject(error)
    }
  )

  return instance
}

// 处理业务错误
const handleBusinessError = (data: ApiResponse) => {
  const { code, message } = data

  switch (code) {
    case 40001:
      ElMessage.error('参数错误')
      break
    case 40003:
      ElMessage.error('权限不足')
      break
    case 40004:
      ElMessage.error('资源不存在')
      break
    case 40005:
      ElMessage.error('操作失败')
      break
    case 50001:
      ElMessage.error('服务器错误')
      break
    default:
      if (message) {
        ElMessage.error(message)
      }
  }
}

// 生成请求ID
const generateRequestId = (): string => {
  return `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
}

// 创建请求实例
const request = createAxiosInstance()

// 测试API连接
export const testApiConnection = async (): Promise<boolean> => {
  try {
    console.log('🔍 [API_TEST] 开始测试API连接')
    console.log('🔍 [API_TEST] 基础URL:', import.meta.env.VITE_API_BASE_URL || '使用代理')
    console.log('🔍 [API_TEST] 代理目标:', 'http://localhost:8000 (根据vite.config.ts)')

    const response = await request.get('/api/health', {
      timeout: 5000,
      skipErrorHandler: true
    })

    console.log('🔍 [API_TEST] 健康检查成功:', response.data)
    return true
  } catch (error: any) {
    console.error('🔍 [API_TEST] 健康检查失败:', error)

    if (error.code === 'ECONNABORTED') {
      console.error('🔍 [API_TEST] 连接超时 - 后端服务可能未启动')
    } else if (error.message === 'Network Error' || error.message.includes('Failed to fetch')) {
      console.error('🔍 [API_TEST] 网络错误 - 后端服务可能未在 http://localhost:8000 运行')
    } else if (error.response?.status === 404) {
      console.error('🔍 [API_TEST] 404错误 - /api/health 端点不存在')
    } else {
      console.error('🔍 [API_TEST] 其他错误:', error.message)
    }

    return false
  }
}

// 请求方法封装
export class ApiClient {
  // GET请求
  static async get<T = any>(
    url: string,
    params?: any,
    config?: RequestConfig
  ): Promise<ApiResponse<T>> {
    const response = await request.get(url, { params, ...config })
    return response.data
  }

  // POST请求
  static async post<T = any>(
    url: string,
    data?: any,
    config?: RequestConfig
  ): Promise<ApiResponse<T>> {
    const response = await request.post(url, data, config)
    return response.data
  }

  // PUT请求
  static async put<T = any>(
    url: string,
    data?: any,
    config?: RequestConfig
  ): Promise<ApiResponse<T>> {
    const response = await request.put(url, data, config)
    return response.data
  }

  // DELETE请求
  static async delete<T = any>(
    url: string,
    config?: RequestConfig
  ): Promise<ApiResponse<T>> {
    const response = await request.delete(url, config)
    return response.data
  }

  // PATCH请求
  static async patch<T = any>(
    url: string,
    data?: any,
    config?: RequestConfig
  ): Promise<ApiResponse<T>> {
    const response = await request.patch(url, data, config)
    return response.data
  }

  // 上传文件
  static async upload<T = any>(
    url: string,
    file: File,
    onProgress?: (progress: number) => void,
    config?: RequestConfig
  ): Promise<ApiResponse<T>> {
    const formData = new FormData()
    formData.append('file', file)

    const response = await request.post(url, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      },
      onUploadProgress: (progressEvent) => {
        if (onProgress && progressEvent.total) {
          const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total)
          onProgress(progress)
        }
      },
      ...config
    })

    return response.data
  }

  // 下载文件
  static async download(
    url: string,
    filename?: string,
    config?: RequestConfig
  ): Promise<void> {
    const response = await request.get(url, {
      responseType: 'blob',
      ...config
    })

    const blob = new Blob([response.data])
    const downloadUrl = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = downloadUrl
    link.download = filename || 'download'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(downloadUrl)
  }
}

export default request
export { request }
