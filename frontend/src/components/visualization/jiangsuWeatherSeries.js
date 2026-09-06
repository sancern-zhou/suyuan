export const weatherParameters = [
  { key: 'windSpeed', label: '风速', unit: 'm/s' },
  { key: 'windDirection', label: '风向', unit: '°' },
  { key: 'temperature', label: '气温', unit: '°C' },
  { key: 'humidity', label: '相对湿度', unit: '%' },
  { key: 'rain', label: '降水量', unit: 'mm' },
  { key: 'pressure', label: '气压', unit: 'hPa' }
]

export const weatherTime = value => Date.parse(String(value || '').replace(' ', 'T'))

export function hourlyWeatherPoints(weather, key) {
  const start = weatherTime(weather?.start)
  const end = weatherTime(weather?.end)
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return []
  const rows = new Map((weather?.data || []).map(row => [weatherTime(row.timePoint), row[key]]))
  const points = []
  for (let time = Math.ceil(start / 3600000) * 3600000; time <= end; time += 3600000) {
    const raw = rows.get(time)
    const value = raw === null || raw === undefined || raw === '' ? null : Number(raw)
    points.push([time, Number.isFinite(value) ? value : null])
  }
  return points
}
