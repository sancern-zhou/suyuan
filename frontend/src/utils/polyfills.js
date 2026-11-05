// 政企内网（麒麟等）常带 Firefox 78~91 ESR，缺 ES2022 API。
// 必须在应用代码前引入：老引擎缺 Array.prototype.at 会让发送消息时的
// 渲染链路抛 TypeError，Vue 补丁中断导致整个消息列表子树被卸载。
/* eslint-disable no-extend-native */

if (!Array.prototype.at) {
  Object.defineProperty(Array.prototype, 'at', {
    value: function at(n) {
      n = Math.trunc(n) || 0
      if (n < 0) n += this.length
      return n < 0 || n >= this.length ? undefined : this[n]
    },
    writable: true,
    enumerable: false,
    configurable: true
  })
}

if (!String.prototype.at) {
  Object.defineProperty(String.prototype, 'at', {
    value: function at(n) {
      n = Math.trunc(n) || 0
      if (n < 0) n += this.length
      return n < 0 || n >= this.length ? undefined : this[n]
    },
    writable: true,
    enumerable: false,
    configurable: true
  })
}

if (!Array.prototype.findLast) {
  Object.defineProperty(Array.prototype, 'findLast', {
    value: function findLast(fn, thisArg) {
      for (let i = this.length - 1; i >= 0; i -= 1) {
        if (fn.call(thisArg, this[i], i, this)) return this[i]
      }
      return undefined
    },
    writable: true,
    enumerable: false,
    configurable: true
  })
}

if (!Array.prototype.findLastIndex) {
  Object.defineProperty(Array.prototype, 'findLastIndex', {
    value: function findLastIndex(fn, thisArg) {
      for (let i = this.length - 1; i >= 0; i -= 1) {
        if (fn.call(thisArg, this[i], i, this)) return i
      }
      return -1
    },
    writable: true,
    enumerable: false,
    configurable: true
  })
}

if (!Object.hasOwn) {
  Object.defineProperty(Object, 'hasOwn', {
    value: (target, key) => Object.prototype.hasOwnProperty.call(Object(target), key),
    writable: true,
    enumerable: false,
    configurable: true
  })
}

// 降级为 JSON 克隆：现有调用点（知识库场景草稿、审核表单）只克隆接口返回的纯 JSON
// 配置对象；不含 Date/Map/Set 时与原语义一致。
if (typeof globalThis.structuredClone !== 'function') {
  globalThis.structuredClone = value => JSON.parse(JSON.stringify(value))
}
