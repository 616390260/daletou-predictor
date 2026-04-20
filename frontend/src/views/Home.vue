<template>
  <div class="container home">
    <section class="hero">
      <div class="hero-badge">
        <span class="dot" />
        {{ meta ? `已分析 ${meta.total_draws} 期历史开奖` : "加载中…" }}
      </div>
      <h1 class="title">
        用 <span class="grad-red">5 种算法</span>
        与 <span class="grad-blue">概率</span>
        赛跑
      </h1>
      <p class="subtitle">
        每期预测 4 注，和真实开奖对比。<br />
        这里不卖号、不卖运气，只验证：
        <b>玄学号、冷热号、记忆号、神经网络，谁都跑不赢随机。</b>
      </p>

      <div v-if="latest" class="latest-card">
        <div class="latest-label">最新开奖 · 第 {{ latest.issue }} 期 · {{ latest.date }}</div>
        <BallRow :front="latest.front" :back="latest.back" />
      </div>
    </section>

    <section class="grid stats-grid" v-if="stats.summary.length">
      <div class="card stat-card" v-for="s in stats.summary" :key="s.model">
        <div class="stat-head">
          <span class="model-badge" :data-model="s.model">{{ s.label }}</span>
          <span class="tag">{{ s.issues }} 期</span>
        </div>
        <div class="stat-main">
          <div class="big">
            {{ (s.hit_rate * 100).toFixed(2) }}<small>%</small>
          </div>
          <div class="label">中奖率</div>
        </div>
        <div class="stat-row">
          <div>
            <div class="mini-label">平均前区命中</div>
            <div class="mini-value">{{ s.avg_front_hit.toFixed(2) }}</div>
          </div>
          <div>
            <div class="mini-label">投入产出</div>
            <div class="mini-value" :class="s.roi >= 0 ? 'up' : 'down'">
              {{ (s.roi * 100).toFixed(1) }}%
            </div>
          </div>
        </div>
      </div>
    </section>

    <section v-else class="loading">正在加载各模型统计…</section>

    <section class="cta-grid">
      <router-link to="/compare" class="card cta">
        <div class="cta-title">模型对比</div>
        <div class="cta-desc">长期命中率曲线 · 投入产出 · 冷热号热力图</div>
        <div class="cta-arrow">→</div>
      </router-link>
      <router-link to="/predictions" class="card cta">
        <div class="cta-title">预测记录</div>
        <div class="cta-desc">每期各模型给出的 4 注号码 + 实际命中</div>
        <div class="cta-arrow">→</div>
      </router-link>
      <router-link to="/history" class="card cta">
        <div class="cta-title">历史开奖</div>
        <div class="cta-desc">近 500 期完整号码 + 销量 + 奖池</div>
        <div class="cta-arrow">→</div>
      </router-link>
    </section>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from "vue";
import { api } from "../api";
import BallRow from "../components/BallRow.vue";

const meta = ref(null);
const history = ref([]);
const stats = ref({ summary: [], trend: {} });

const latest = computed(() => history.value[0] || null);

onMounted(async () => {
  const [m, h, s] = await Promise.all([api.meta(), api.history(), api.stats()]);
  meta.value = m;
  history.value = h || [];
  stats.value = s || { summary: [], trend: {} };
});
</script>

<style scoped>
.home {
  display: flex;
  flex-direction: column;
  gap: 40px;
}

.hero {
  text-align: center;
  padding: 32px 0 16px;
}

.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: 99px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--border);
  font-size: 13px;
  color: var(--text-2);
  margin-bottom: 24px;
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--green);
  box-shadow: 0 0 8px var(--green);
}

.title {
  font-size: clamp(32px, 6vw, 60px);
  font-weight: 800;
  letter-spacing: -0.03em;
  line-height: 1.05;
  margin-bottom: 20px;
}

.grad-red {
  background: var(--grad-primary);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.grad-blue {
  background: var(--grad-blue);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.subtitle {
  font-size: 16px;
  color: var(--text-2);
  max-width: 640px;
  margin: 0 auto 40px;
}

.subtitle b {
  color: var(--text-1);
}

.latest-card {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 20px 28px;
  border-radius: var(--radius-lg);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0.015));
  border: 1px solid var(--border);
  box-shadow: var(--shadow-md);
}

.latest-label {
  font-size: 12px;
  color: var(--text-3);
  font-family: var(--font-mono);
  letter-spacing: 0.04em;
}

.grid {
  display: grid;
  gap: 16px;
}

.stats-grid {
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.stat-card {
  padding: 20px;
}

.stat-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.model-badge {
  font-size: 12px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-1);
}
.model-badge[data-model="random"] { background: rgba(113, 113, 122, 0.2); color: #d4d4d8; }
.model-badge[data-model="frequency"] { background: rgba(59, 130, 246, 0.2); color: #93c5fd; }
.model-badge[data-model="bayesian"] { background: rgba(6, 182, 212, 0.2); color: #67e8f9; }
.model-badge[data-model="markov"] { background: rgba(168, 85, 247, 0.2); color: #d8b4fe; }
.model-badge[data-model="lstm"] { background: rgba(236, 72, 153, 0.2); color: #f9a8d4; }
.model-badge[data-model="genetic"] { background: rgba(16, 185, 129, 0.2); color: #6ee7b7; }
.model-badge[data-model="ensemble"] { background: rgba(245, 158, 11, 0.2); color: #fcd34d; }

.stat-main .big {
  font-size: 36px;
  font-weight: 800;
  letter-spacing: -0.02em;
  font-family: var(--font-mono);
}

.stat-main .big small {
  font-size: 16px;
  color: var(--text-3);
  font-weight: 600;
}

.stat-main .label {
  font-size: 12px;
  color: var(--text-3);
  margin-bottom: 16px;
}

.stat-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
}

.mini-label {
  font-size: 11px;
  color: var(--text-3);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.mini-value {
  font-size: 16px;
  font-weight: 600;
  font-family: var(--font-mono);
  margin-top: 2px;
}

.mini-value.up { color: var(--green); }
.mini-value.down { color: var(--red); }

.cta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 16px;
}

.cta {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 24px;
  text-decoration: none;
  color: inherit;
}

.cta-title {
  font-size: 17px;
  font-weight: 700;
  margin-bottom: 4px;
}

.cta-desc {
  font-size: 13px;
  color: var(--text-3);
  line-height: 1.5;
  flex: 1;
}

.cta-arrow {
  font-size: 24px;
  color: var(--text-3);
  transition: transform 0.2s ease, color 0.2s ease;
}

.cta:hover .cta-arrow {
  color: var(--text-1);
  transform: translateX(4px);
}

.cta > div:nth-child(1),
.cta > div:nth-child(2) {
  flex: 1;
}
</style>
