import { downloadResource } from './resourceDownloads.js'


export const fileManagerDownloadUrl = path => {
  const params = new URLSearchParams({ path: String(path || '') })
  return `/api/file-manager/download?${params.toString()}`
}


export const downloadManagedFile = (item, runtime = {}) => {
  if (!item?.path) throw new Error('文件路径无效')
  const downloadImpl = runtime.downloadImpl || downloadResource
  const label = item.name || String(item.path).split('/').pop() || 'download'
  return downloadImpl({
    label,
    download_url: fileManagerDownloadUrl(item.path)
  }, runtime.downloadRuntime)
}
