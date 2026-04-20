<template>
  <header class="header">
    <div class="container header-inner">
      <router-link to="/" class="brand">
        <span class="logo">乐</span>
        <span class="brand-text">
          <b>大乐透预测实验室</b>
          <small>Data-Driven Lottery Lab</small>
        </span>
      </router-link>

      <nav class="nav">
        <router-link
          v-for="item in navs"
          :key="item.to"
          :to="item.to"
          class="nav-link"
          active-class="active"
        >
          {{ item.label }}
        </router-link>
      </nav>
    </div>
  </header>
</template>

<script setup>
const navs = [
  { to: "/", label: "首页" },
  { to: "/history", label: "历史开奖" },
  { to: "/predictions", label: "预测记录" },
  { to: "/analysis", label: "命中分析" },
  { to: "/compare", label: "模型对比" },
  { to: "/about", label: "关于" },
];
</script>

<style scoped>
.header {
  position: sticky;
  top: 0;
  z-index: 10;
  padding: 16px 0;
  background: rgba(10, 10, 15, 0.7);
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 1px solid var(--border);
}

.header-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: var(--grad-primary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 900;
  color: #fff;
  font-size: 20px;
  box-shadow: 0 4px 12px rgba(239, 68, 68, 0.3);
}

.brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.1;
}

.brand-text b {
  font-size: 15px;
  font-weight: 700;
}

.brand-text small {
  font-size: 11px;
  color: var(--text-3);
  font-family: var(--font-mono);
  letter-spacing: 0.04em;
}

.nav {
  display: flex;
  gap: 4px;
}

.nav-link {
  padding: 8px 14px;
  border-radius: 99px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-2);
  transition: all 0.15s ease;
}

.nav-link:hover {
  color: var(--text-1);
  background: rgba(255, 255, 255, 0.04);
}

.nav-link.active {
  color: var(--text-1);
  background: rgba(255, 255, 255, 0.08);
  box-shadow: inset 0 0 0 1px var(--border-strong);
}

@media (max-width: 768px) {
  .brand-text small {
    display: none;
  }
  .brand-text b {
    font-size: 13px;
  }
  .nav {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    max-width: 60vw;
  }
  .nav-link {
    padding: 6px 10px;
    font-size: 12px;
    flex-shrink: 0;
  }
}
</style>
