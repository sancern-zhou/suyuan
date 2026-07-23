export function completeUploadedAttachment(attachmentList, pendingAttachment, uploadResult) {
  const resourceRefId = uploadResult?.resource_ref?.ref_id
  if (!resourceRefId) {
    throw new Error('文件上传结果缺少对话资源引用')
  }

  const index = attachmentList.indexOf(pendingAttachment)
  if (index < 0) {
    throw new Error('文件上传完成，但待更新附件不存在')
  }

  const completedAttachment = {
    ...attachmentList[index],
    file_id: uploadResult.file_id,
    resourceRefId,
    url: uploadResult.url,
    mime_type: uploadResult.mime_type || pendingAttachment.file?.type || null,
    size: uploadResult.file_size || pendingAttachment.file?.size || pendingAttachment.size,
    uploading: false
  }
  attachmentList.splice(index, 1, completedAttachment)
  return completedAttachment
}
