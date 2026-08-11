export const PREFERRED_CHART_FONT_FAMILY = [
  'FZXiaoBiaoSong-B05S',
  '方正小标宋简体',
  'PingFang SC',
  'Hiragino Sans GB',
  'Microsoft YaHei',
  'Noto Sans CJK SC',
  'Helvetica Neue',
  'Arial',
  'sans-serif'
].join(', ')

export function applyPreferredChartFont(option) {
  if (!option || typeof option !== 'object' || Array.isArray(option)) return option
  return {
    ...option,
    textStyle: {
      ...(option.textStyle || {}),
      fontFamily: PREFERRED_CHART_FONT_FAMILY
    }
  }
}
