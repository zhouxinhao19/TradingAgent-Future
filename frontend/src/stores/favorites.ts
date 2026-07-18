import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { favoritesApi, type FavoriteItem, type AddFavoriteParams } from '@/api/favorites'

export const useFavoritesStore = defineStore('favorites', () => {
  const items = ref<FavoriteItem[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Getters
  const stockItems = computed(() => items.value.filter(i => i.asset_type === 'stock'))
  const commodityItems = computed(() => items.value.filter(i => i.asset_type === 'commodity'))
  const count = computed(() => items.value.length)

  function isFavorited(assetType: 'stock' | 'commodity', code: string): boolean {
    if (assetType === 'stock') {
      return items.value.some(i => i.asset_type === 'stock' && i.stock_code === code)
    }
    return items.value.some(i => i.asset_type === 'commodity' && i.full_symbol === code)
  }

  // Actions
  async function loadFavorites(assetType?: string) {
    loading.value = true
    error.value = null
    try {
      const r = await favoritesApi.list(assetType)
      items.value = r?.data ?? []
    } catch (e: any) {
      error.value = String(e)
      console.error('加载自选品种失败:', e)
      items.value = []
    } finally {
      loading.value = false
    }
  }

  async function addFavorite(params: AddFavoriteParams): Promise<boolean> {
    try {
      const r = await favoritesApi.add(params)
      if (r?.success !== false) {
        await loadFavorites()
        return true
      }
      return false
    } catch (e) {
      console.error('添加自选失败:', e)
      return false
    }
  }

  async function removeFavorite(id: string): Promise<boolean> {
    try {
      const r = await favoritesApi.remove(id)
      if (r?.success !== false) {
        items.value = items.value.filter(i => i.id !== id)
        return true
      }
      return false
    } catch (e) {
      console.error('删除自选失败:', e)
      return false
    }
  }

  async function batchRemove(ids: string[]): Promise<boolean> {
    try {
      const r = await favoritesApi.batchRemove(ids)
      if (r?.success !== false) {
        items.value = items.value.filter(i => !ids.includes(i.id))
        return true
      }
      return false
    } catch (e) {
      console.error('批量删除失败:', e)
      return false
    }
  }

  async function updateFavorite(id: string, updates: Record<string, any>): Promise<boolean> {
    try {
      const r = await favoritesApi.update(id, updates as any)
      if (r?.success !== false) {
        await loadFavorites()
        return true
      }
      return false
    } catch (e) {
      console.error('更新自选失败:', e)
      return false
    }
  }

  return {
    items, loading, error,
    stockItems, commodityItems, count, isFavorited,
    loadFavorites, addFavorite, removeFavorite, batchRemove, updateFavorite,
  }
})
