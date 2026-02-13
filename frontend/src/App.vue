<template>
  <div id="app">
    <router-view />
  </div>
</template>

<script setup>
</script>

<style lang="scss">
.top-nav {
  background: #2c3e50;
  color: white;
  padding: 0;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  flex-shrink: 0;

  .nav-container {
    max-width: 1200px;
    margin: 0 auto;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0 20px;
    height: 60px;
  }

  .nav-brand h2 {
    margin: 0;
    font-size: 20px;
    font-weight: 600;
  }

  .nav-links {
    display: flex;
    gap: 8px;
  }

  .nav-link {
    color: rgba(255, 255, 255, 0.8);
    text-decoration: none;
    padding: 8px 16px;
    border-radius: 4px;
    transition: all 0.2s;
    font-size: 14px;

    &:hover {
      background: rgba(255, 255, 255, 0.1);
      color: white;
    }

    &.active {
      background: rgba(255, 255, 255, 0.2);
      color: white;
    }
  }
}

#app {
  min-height: 100vh;
  background: #f5f5f5;
}
</style>
