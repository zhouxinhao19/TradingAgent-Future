// 市场参数规范化：将各类板块/交易所/缩写统一为分析模块支持的 A股/美股/港股
export const normalizeMarketForAnalysis = (market: any): string => {
  const raw = String(market ?? '').trim()
  const upper = raw.toUpperCase()
  const cn = raw
  const isA = [
    'A股', '主板', '创业板', '科创板', '中小板', '沪市', '深市', '上交所', '深交所', '北交所'
  ].includes(cn) || ['CN', 'SH', 'SZ', 'SSE', 'SZSE'].includes(upper)
  const isHK = ['港股', '港交所'].includes(cn) || ['HK', 'HKEX'].includes(upper)
  const isUS = ['美股', '纳斯达克', '纽交所'].includes(cn) || ['US', 'NASDAQ', 'NYSE', 'AMEX'].includes(upper)
  if (isA) return 'A股'
  if (isHK) return '港股'
  if (isUS) return '美股'
  // 默认按A股处理
  return 'A股'
}

export default {
  normalizeMarketForAnalysis
}

