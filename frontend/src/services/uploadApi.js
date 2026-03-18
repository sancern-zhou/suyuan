/**
 * 文件上传API服务
 * 用于对话中的文件和图片上传
 */

// 使用相对路径，通过vite proxy转发到后端
// 开发环境: /api -> http://localhost:8000 (vite proxy)
// 生产环境: 需要配置反向代理将 /api 转发到后端

/**
 * 上传文件用于对话
 * @param {File} file - 要上传的文件
 * @param {string} sessionId - 可选的会话ID
 * @returns {Promise<Object>} 上传结果
 */
export async function uploadChatFile(file, sessionId = null) {
  const formData = new FormData();
  formData.append('file', file);

  if (sessionId) {
    formData.append('session_id', sessionId);
  }

  try {
    console.log('[uploadChatFile] 上传文件:', file.name, '大小:', file.size, '类型:', file.type);
    console.log('[uploadChatFile] sessionId:', sessionId);

    const response = await fetch('/api/upload/chat', {
      method: 'POST',
      body: formData,
      // 不设置Content-Type，让浏览器自动处理multipart/form-data边界
    });

    console.log('[uploadChatFile] 响应状态:', response.status, response.statusText);

    if (!response.ok) {
      // 尝试解析JSON错误响应
      let errorMessage = '文件上传失败';
      try {
        const contentType = response.headers.get('content-type');
        console.log('[uploadChatFile] 错误响应 Content-Type:', contentType);

        const responseText = await response.text();
        console.log('[uploadChatFile] 错误响应内容:', responseText);

        if (contentType && contentType.includes('application/json')) {
          try {
            const errorData = JSON.parse(responseText);
            errorMessage = errorData.detail || errorData.message || responseText;
          } catch (e) {
            errorMessage = responseText;
          }
        } else {
          errorMessage = responseText || `HTTP ${response.status}: ${response.statusText}`;
        }
      } catch (parseError) {
        // 读取响应失败
        errorMessage = `HTTP ${response.status}: ${response.statusText}`;
        console.error('[uploadChatFile] 解析错误响应失败:', parseError);
      }
      throw new Error(errorMessage);
    }

    return await response.json();
  } catch (error) {
    console.error('Upload error:', error);
    throw error;
  }
}

/**
 * 获取文件信息
 * @param {string} fileId - 文件ID
 * @returns {Promise<Object>} 文件信息
 */
export async function getFileInfo(fileId) {
  const response = await fetch(`/api/upload/${fileId}/info`);

  if (!response.ok) {
    throw new Error('获取文件信息失败');
  }

  return await response.json();
}

/**
 * 删除上传的文件
 * @param {string} fileId - 文件ID
 * @returns {Promise<Object>} 删除结果
 */
export async function deleteChatFile(fileId) {
  const response = await fetch(`/api/upload/${fileId}`, {
    method: 'DELETE',
  });

  if (!response.ok) {
    throw new Error('删除文件失败');
  }

  return await response.json();
}

/**
 * 获取文件URL
 * @param {string} fileId - 文件ID
 * @returns {string} 文件访问URL
 */
export function getFileUrl(fileId) {
  return `/api/upload/${fileId}`;
}

/**
 * 验证文件类型
 * @param {File} file - 要验证的文件
 * @returns {Object} 验证结果 {valid: boolean, message: string, category: string}
 */
export function validateFile(file) {
  const maxSize = {
    image: 5 * 1024 * 1024, // 5MB
    document: 50 * 1024 * 1024, // 50MB
  };

  const imageTypes = ['image/png', 'image/jpeg', 'image/jpg', 'image/gif', 'image/bmp', 'image/webp'];
  const documentTypes = [
    'application/pdf',
    'text/plain',
    'text/markdown',
    'application/json',
    'text/csv',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  ];

  // 文件扩展名映射（备用检查，因为MIME类型在不同系统上可能不一致）
  const extensionMap = {
    // 图片
    '.png': 'image',
    '.jpg': 'image',
    '.jpeg': 'image',
    '.gif': 'image',
    '.bmp': 'image',
    '.webp': 'image',
    // 文档
    '.pdf': 'document',
    '.txt': 'document',
    '.md': 'document',
    '.markdown': 'document',
    '.json': 'document',
    '.csv': 'document',
    '.docx': 'document',
    '.xlsx': 'document',
    '.pptx': 'document',
  };

  // 首先通过 MIME 类型检查
  const isImage = imageTypes.includes(file.type);
  const isDocument = documentTypes.includes(file.type);

  let category = null;

  if (isImage) {
    category = 'image';
  } else if (isDocument) {
    category = 'document';
  } else {
    // MIME 类型检查失败，尝试通过文件扩展名检查
    const fileName = file.name.toLowerCase();
    const ext = Object.keys(extensionMap).find(e => fileName.endsWith(e));

    if (!ext) {
      return {
        valid: false,
        message: `不支持的文件类型: ${file.type || '未知'}`
      };
    }
    category = extensionMap[ext];
  }

  const limit = maxSize[category];

  if (file.size > limit) {
    const limitMB = limit / 1024 / 1024;
    return {
      valid: false,
      message: `文件过大。${category === 'image' ? '图片' : '文档'}最大允许 ${limitMB}MB`
    };
  }

  return {
    valid: true,
    category
  };
}

/**
 * 创建图片预览URL
 * @param {File} file - 图片文件
 * @returns {Promise<string>} Data URL
 */
export function createImagePreview(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => resolve(e.target.result);
    reader.onerror = (e) => reject(e);
    reader.readAsDataURL(file);
  });
}

export default {
  uploadChatFile,
  getFileInfo,
  deleteChatFile,
  getFileUrl,
  validateFile,
  createImagePreview,
};
