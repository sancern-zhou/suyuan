# Vue3 迁移 - 手动执行指南

由于自动化脚本遇到编码问题，请手动执行以下步骤完成迁移。

## 第一步：复制可复用资源

请手动复制以下文件：

### 1. 复制 types/api.ts
```bash
copy "D:\溯源\frontend\src\types\api.ts" "D:\溯源\frontend-vue\src\types\api.ts"
```

### 2. 复制 services/api.ts
```bash
copy "D:\溯源\frontend\src\services\api.ts" "D:\溯源\frontend-vue\src\services\api.ts"
```

### 3. 复制 styles 目录
```bash
xcopy /E /I /Y "D:\溯源\frontend\src\styles" "D:\溯源\frontend-vue\src\styles"
```

## 第二步：创建 main.ts

在 `D:\溯源\frontend-vue\src\main.ts` 创建以下内容：

```typescript
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import Antd from 'ant-design-vue'
import App from './App.vue'

import 'ant-design-vue/dist/reset.css'
import './styles/theme.css'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(Antd)

app.mount('#app')
```

## 第三步：复制示例组件

从 `D:\溯源\vue3-examples\` 复制以下文件到对应位置：

### 组件
```bash
copy "D:\溯源\vue3-examples\components\KpiStrip.vue" "D:\溯源\frontend-vue\src\components\"
copy "D:\溯源\vue3-examples\components\ChartsPanel.vue" "D:\溯源\frontend-vue\src\components\"
copy "D:\溯源\vue3-examples\components\MapPanel.vue" "D:\溯源\frontend-vue\src\components\"
```

### Composables
```bash
copy "D:\溯源\vue3-examples\composables\useAMapLoader.ts" "D:\溯源\frontend-vue\src\composables\"
```

### Stores
```bash
copy "D:\溯源\vue3-examples\stores\analysis.ts" "D:\溯源\frontend-vue\src\stores\"
```

### App.vue
```bash
copy "D:\溯源\vue3-examples\App.vue" "D:\溯源\frontend-vue\src\App.vue"
```

## 第四步：手动创建剩余组件

请参考原React组件，手动创建以下Vue3组件。每个组件的迁移模板如下：

### TextPanel.vue
### FloatingChatButton.vue
### ModuleCard.vue
### ChatOverlay.vue
### VisualRenderer.vue
### StreamProgress.vue
### ChatMessageRenderer.vue
### QueryBar.vue

详细迁移方法请参考 `VUE3_MIGRATION_PLAN.md` 第5章。

## 第五步：测试

```bash
cd D:\溯源\frontend-vue
npm run dev
```

访问 http://localhost:5174 测试。

## 需要帮助?

如果您不想手动执行这些步骤，请告诉我具体需要创建哪些文件，我会为您逐个创建。
