<template>
  <section class="focus-carousel">
    <header class="panel-title">
      <span class="title-bar" aria-hidden="true"></span>
      <h3>{{ currentSlide.title }}</h3>
      <div class="carousel-controls">
        <span class="slide-dots" aria-hidden="true">
          <i
            v-for="(slide, index) in slides"
            :key="slide.key"
            :class="{ on: index === currentIndex }"
            @click="jumpTo(index)"
          ></i>
        </span>
        <button type="button" class="pause-btn" @click="paused = !paused">
          {{ paused ? '播放' : '暂停' }}
        </button>
      </div>
    </header>

    <div class="carousel-stage">
      <!-- 地图页：复用站点态势地图 -->
      <div v-show="currentSlide.key === 'map'" class="slide slide-map">
        <slot />
      </div>
      <!-- 图片页：轨迹 / 卫星素材 -->
      <div
        v-for="slide in imageSlides"
        :key="slide.key"
        v-show="currentSlide.key === slide.key"
        class="slide slide-image"
      >
        <img
          :src="slide.url"
          :alt="slide.title"
          loading="lazy"
          @error="onImageError(slide)"
        />
        <small class="slide-caption">{{ slide.caption }}</small>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  assets: { type: Array, default: () => [] },
  assetUrl: { type: Function, required: true },
  // 每页停留秒数
  intervalSeconds: { type: Number, default: 20 }
})

const MAP_SLIDE_KEY = 'map'
const currentIndex = ref(0)
const paused = ref(false)
const brokenKeys = ref(new Set())
let timer = null

const imageSlides = computed(() =>
  props.assets
    .filter(item => item.kind && item.asset_path)
    .map(item => ({
      key: item.asset_path,
      kind: item.kind,
      title: item.title || (item.kind === 'transport' ? '传输轨迹分析' : '卫星遥感'),
      caption: `${item.title || ''} · ${String(item.taken_at || '').replace('T', ' ').slice(5, 16)}`,
      url: props.assetUrl(item.asset_path)
    }))
    .filter(slide => !brokenKeys.value.has(slide.key))
)

const slides = computed(() => [{ key: MAP_SLIDE_KEY, title: '站点实时态势' }, ...imageSlides.value])
const currentSlide = computed(() => slides.value[Math.min(currentIndex.value, slides.value.length - 1)] || slides.value[0])

const startTimer = () => {
  if (timer) clearInterval(timer)
  timer = setInterval(() => {
    if (paused.value || slides.value.length <= 1) return
    currentIndex.value = (currentIndex.value + 1) % slides.value.length
  }, props.intervalSeconds * 1000)
}

const jumpTo = index => {
  currentIndex.value = index
  paused.value = false
}

const onImageError = slide => {
  const next = new Set(brokenKeys.value)
  next.add(slide.key)
  brokenKeys.value = next
}

onMounted(startTimer)
onBeforeUnmount(() => timer && clearInterval(timer))
watch(() => props.assets, () => {
  // 素材刷新后停在有效页
  if (currentIndex.value >= slides.value.length) currentIndex.value = 0
})
watch(imageSlides, () => { /* 模板响应式依赖 */ }, { immediate: true })
</script>

<style lang="scss" scoped>
.focus-carousel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 12px 14px;
  border: 1px solid rgba(63, 200, 212, 0.18);
  border-radius: 8px;
  background: rgba(7, 41, 59, 0.55);
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;

  .title-bar {
    width: 4px;
    height: 14px;
    border-radius: 2px;
    background: #3fc8d4;
  }
  h3 {
    margin: 0;
    font-size: 15px;
    color: #eaf6f8;
    letter-spacing: 1px;
  }
}

.carousel-controls {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-left: auto;

  .slide-dots {
    display: inline-flex;
    gap: 5px;

    i {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: rgba(138, 182, 194, 0.35);
      cursor: pointer;
      transition: all 0.25s;

      &.on {
        background: #3fc8d4;
        box-shadow: 0 0 6px rgba(63, 200, 212, 0.8);
      }
    }
  }

  .pause-btn {
    padding: 2px 10px;
    border: 1px solid rgba(63, 200, 212, 0.3);
    border-radius: 4px;
    background: transparent;
    color: #8ab6c2;
    font-size: 11px;
    cursor: pointer;

    &:hover { color: #3fc8d4; }
  }
}

.carousel-stage {
  flex: 1;
  min-height: 0;
  position: relative;
}

.slide {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
}

.slide-image {
  align-items: center;
  justify-content: center;

  img {
    max-width: 100%;
    max-height: calc(100% - 22px);
    object-fit: contain;
    border-radius: 4px;
  }
  .slide-caption {
    margin-top: 4px;
    font-size: 11px;
    color: #6f95a3;
  }
}
</style>
