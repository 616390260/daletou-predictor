<template>
  <div class="container home">
    <!-- Hero -->
    <section class="hero">
      <div class="hero-badge">
        <span class="dot" />
        {{ meta ? `已分析 ${meta.total_draws} 期 · 9 模型 · 数据更新于 ${formatTime(meta.generated_at)}` : "加载中…" }}
      </div>
      <h1 class="title">
        让算法和 <span class="grad-red">概率</span> 掰手腕
      </h1>
      <p class="subtitle">
        每期 9 个模型各投 4 注，开奖后透明公布命中率。<br />
        <b>验证"预测"到底比随机强多少。</b>
      </p>
    </section>

    <!-- 顶部三大卡：倒计时 / 最新开奖 / 累计 ROI -->
    <section class="top-grid">
      <!-- 下次开奖倒计时 -->
      <div class="card highlight-card countdown-card" v-if="meta?.next_draw_at">
        <div class="card-label">下一期开奖倒计时</div>
        <div class="countdown">
          <div class="cd-item"><span class="cd-val">{{ cd.d }}</span><span class="cd-unit">天</span></div>
          <div class="cd-item"><span class="cd-val">{{ cd.h }}</span><span class="cd-unit">时</span></div>
          <div class="cd-item"><span class="cd-val">{{ cd.m }}</span><span class="cd-unit">分</span></div>
          <div class="cd-item"><span class="cd-val">{{ cd.s }}</span><span class="cd-unit">秒</span></div>
        </div>
        <div class="card-sub">
          <span>预测期：第 {{ meta.predicting_issue || "—" }} 期</span>
          <span>开奖时间：{{ formatFull(meta.next_draw_at) }}</span>
        </div>
      </div>

      <!-- 最新开奖 -->
      <div class="card highlight-card" v-if="latest">
        <div class="card-label">最近一次开奖 · 第 {{ latest.issue }} 期 · {{ latest.date }}</div>
        <div class="latest-ball-wrap">
          <BallRow :front="latest.front" :back="latest.back" size="lg" />
        </div>
        <div class="card-sub">
          <span v-if="latest.sales">销量 ¥{{ (latest.sales / 1e8).toFixed(2) }} 亿</span>
          <span v-if="latest.pool">奖池 ¥{{ (latest.pool / 1e8).toFixed(2) }} 亿</span>
        </div>
      </div>

      <!-- 累计表现 -->
      <div class="card highlight-card" v-if="totalStats">
        <div class="card-label">累计表现（全部模型）</div>
        <div class="kpi-grid">
          <div>
            <div class="kpi-val">{{ totalStats.issues }}</div>
            <div class="kpi-label">评估期数</div>
          </div>
          <div>
            <div class="kpi-val">{{ totalStats.winTickets }}<small>/{{ totalStats.totalTickets }}</small></div>
            <div class="kpi-label">命中/总注数</div>
          </div>
          <div>
            <div class="kpi-val" :class="totalStats.roi >= 0 ? 'up' : 'down'">
              {{ (totalStats.roi * 100).toFixed(1) }}<small>%</small>
            </div>
            <div class="kpi-label">累计 ROI</div>
          </div>
        </div>
      </div>
    </section>

    <!-- 上期命中回顾 -->
    <section class="card" v-if="lastReview">
      <div class="section-title">
        <h2>上期命中回顾 · 第 {{ lastReview.issue }} 期</h2>
        <router-link to="/predictions" class="see-all">全部记录 →</router-link>
      </div>
      <div class="review-head">
        <div class="review-actual">
          <div class="card-label">实际开奖</div>
          <BallRow :front="lastReview.real.front" :back="lastReview.real.back" size="md" />
        </div>
        <div class="review-summary">
          <div>
            <div class="kpi-val" :class="lastReview.winModels > 0 ? 'up' : 'down'">
              {{ lastReview.winModels }}<small>/{{ lastReview.totalModels }}</small>
            </div>
            <div class="kpi-label">中奖模型</div>
          </div>
          <div>
            <div class="kpi-val">{{ lastReview.winTickets }}<small>/{{ lastReview.totalTickets }}</small></div>
            <div class="kpi-label">中奖注数</div>
          </div>
          <div>
            <div class="kpi-val" :class="lastReview.roi >= 0 ? 'up' : 'down'">
              {{ (lastReview.roi * 100).toFixed(0) }}<small>%</small>
            </div>
            <div class="kpi-label">本期 ROI</div>
          </div>
        </div>
      </div>
      <div class="review-grid">
        <div
          class="review-tile"
          v-for="m in lastReview.models"
          :key="m.model"
          :class="{ 'is-win': m.winTickets > 0 }"
        >
          <div class="review-tile-head">
            <span class="model-badge" :data-model="m.model">{{ m.label }}</span>
            <span class="review-tag" :class="m.winTickets > 0 ? 'up' : 'down'">
              {{ m.winTickets }}/{{ m.tickets.length }}
            </span>
          </div>
          <div class="review-tile-tickets">
            <BallRow
              v-for="t in m.tickets"
              :key="t.idx"
              :front="t.front"
              :back="t.back"
              :hit-front="lastReview.real.front"
              :hit-back="lastReview.real.back"
              size="xs"
            />
          </div>
        </div>
      </div>
    </section>

    <!-- 本期预测概览 -->
    <section class="card" v-if="nextPrediction">
      <div class="section-title">
        <h2>第 {{ nextPrediction.issue }} 期预测</h2>
        <router-link to="/predictions" class="see-all">查看全部 →</router-link>
      </div>
      <div class="predict-grid">
        <div
          class="predict-tile"
          v-for="m in nextPrediction.models"
          :key="m.model"
        >
          <div class="predict-tile-head">
            <span class="model-badge" :data-model="m.model">{{ m.label }}</span>
          </div>
          <div class="predict-tile-tickets">
            <BallRow
              v-for="t in m.tickets"
              :key="t.idx"
              :front="t.front"
              :back="t.back"
              size="xs"
            />
          </div>
        </div>
      </div>
    </section>

    <!-- 各模型 KPI 汇总 -->
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

    <section v-else class="loading">
      各模型尚无评估记录，等下一期开奖后将自动填充 📊
    </section>

    <section class="cta-grid">
      <router-link to="/compare" class="card cta">
        <div>
          <div class="cta-title">模型对比</div>
          <div class="cta-desc">9 模型长期命中率 · ROI · 冷热号热力图</div>
        </div>
        <div class="cta-arrow">→</div>
      </router-link>
      <router-link to="/predictions" class="card cta">
        <div>
          <div class="cta-title">预测记录</div>
          <div class="cta-desc">每期 9 模型 × 4 注号码及命中详情</div>
        </div>
        <div class="cta-arrow">→</div>
      </router-link>
      <router-link to="/history" class="card cta">
        <div>
          <div class="cta-title">历史开奖</div>
          <div class="cta-desc">近 500 期完整号码 + 销量 + 奖池</div>
        </div>
        <div class="cta-arrow">→</div>
      </router-link>
    </section>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, computed } from "vue";
import { api } from "../api";
import BallRow from "../components/BallRow.vue";

const meta = ref(null);
const history = ref([]);
const stats = ref({ summary: [], trend: {} });
const predictions = ref([]);
const now = ref(new Date());

let timer = null;

const latest = computed(() => history.value[0] || null);

const nextPrediction = computed(() => {
  if (!predictions.value.length) return null;
  const issue = meta.value?.predicting_issue;
  const target = predictions.value.find((p) => p.issue === issue) || predictions.value[0];
  return target;
});

const lastReview = computed(() => {
  const item = predictions.value.find(
    (p) => p.real && p.models.some((m) => m.tickets.some((t) => t.result)),
  );
  if (!item) return null;
  const models = item.models.map((m) => {
    const winTickets = m.tickets.filter((t) => t.result && t.result.amount > 0).length;
    return { ...m, winTickets };
  });
  const totalTickets = models.reduce((s, m) => s + m.tickets.length, 0);
  const winTickets = models.reduce((s, m) => s + m.winTickets, 0);
  const winModels = models.filter((m) => m.winTickets > 0).length;
  const cost = totalTickets * 2;
  const prize = models.reduce(
    (s, m) => s + m.tickets.reduce((ss, t) => ss + (t.result?.amount || 0), 0),
    0,
  );
  return {
    issue: item.issue,
    real: item.real,
    models,
    totalModels: models.length,
    winModels,
    totalTickets,
    winTickets,
    roi: cost ? (prize - cost) / cost : 0,
  };
});

const totalStats = computed(() => {
  if (!stats.value.summary.length) return null;
  let tickets = 0, wins = 0, cost = 0, prize = 0;
  let issues = 0;
  for (const s of stats.value.summary) {
    tickets += s.tickets;
    wins += s.win_tickets;
    cost += s.cost;
    prize += s.total_prize;
    if (s.issues > issues) issues = s.issues;
  }
  return {
    totalTickets: tickets,
    winTickets: wins,
    cost,
    prize,
    roi: cost ? (prize - cost) / cost : 0,
    issues,
  };
});

const cd = computed(() => {
  if (!meta.value?.next_draw_at) return { d: "--", h: "--", m: "--", s: "--" };
  const target = new Date(meta.value.next_draw_at).getTime();
  const diff = Math.max(0, target - now.value.getTime());
  const d = Math.floor(diff / 86400000);
  const h = Math.floor((diff % 86400000) / 3600000);
  const m = Math.floor((diff % 3600000) / 60000);
  const s = Math.floor((diff % 60000) / 1000);
  const pad = (n) => String(n).padStart(2, "0");
  return { d: pad(d), h: pad(h), m: pad(m), s: pad(s) };
});

function formatTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function formatFull(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

onMounted(async () => {
  const [m, h, s, p] = await Promise.all([
    api.meta(),
    api.history(),
    api.stats(),
    api.predictions(),
  ]);
  meta.value = m;
  history.value = h || [];
  stats.value = s || { summary: [], trend: {} };
  predictions.value = p || [];
  timer = setInterval(() => (now.value = new Date()), 1000);
});

onBeforeUnmount(() => {
  if (timer) clearInterval(timer);
});
</script>

<style scoped>
.home {
  display: flex;
  flex-direction: column;
  gap: 32px;
}

.hero {
  text-align: center;
  padding: 24px 0 8px;
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
  margin-bottom: 20px;
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--green);
  box-shadow: 0 0 8px var(--green);
}

.title {
  font-size: clamp(30px, 5.5vw, 54px);
  font-weight: 800;
  letter-spacing: -0.03em;
  line-height: 1.1;
  margin-bottom: 16px;
}

.grad-red {
  background: var(--grad-primary);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.subtitle {
  font-size: 15px;
  color: var(--text-2);
  max-width: 580px;
  margin: 0 auto;
  line-height: 1.6;
}
.subtitle b { color: var(--text-1); }

/* 顶部三大卡 */
.top-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
}

.highlight-card {
  padding: 22px 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 180px;
  justify-content: space-between;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0.015));
  border: 1px solid var(--border);
}

.card-label {
  font-size: 12px;
  color: var(--text-3);
  letter-spacing: 0.05em;
  text-transform: uppercase;
  font-family: var(--font-mono);
}

.card-sub {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--text-3);
  flex-wrap: wrap;
}

/* 倒计时 */
.countdown-card { background: linear-gradient(135deg, rgba(239, 68, 68, 0.14), rgba(245, 158, 11, 0.08)); }

.countdown {
  display: flex;
  gap: 12px;
  justify-content: flex-start;
  align-items: baseline;
}

.cd-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 52px;
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.35);
}

.cd-val {
  font-size: 26px;
  font-weight: 800;
  color: var(--text-1);
  font-family: var(--font-mono);
  line-height: 1;
}

.cd-unit {
  font-size: 11px;
  color: var(--text-3);
  margin-top: 4px;
  letter-spacing: 0.1em;
}

.latest-ball-wrap {
  display: flex;
  justify-content: flex-start;
  align-items: center;
}

/* 累计表现 */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.kpi-val {
  font-size: 24px;
  font-weight: 800;
  font-family: var(--font-mono);
  letter-spacing: -0.02em;
  line-height: 1.1;
}
.kpi-val small {
  font-size: 13px;
  color: var(--text-3);
  font-weight: 600;
  margin-left: 2px;
}
.kpi-val.up { color: var(--green); }
.kpi-val.down { color: var(--red); }

.kpi-label {
  font-size: 11px;
  color: var(--text-3);
  margin-top: 4px;
  letter-spacing: 0.04em;
}

/* 上期命中回顾 */
.review-head {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 24px;
  align-items: center;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.02);
  margin-bottom: 16px;
}

.review-actual .card-label {
  margin-bottom: 8px;
}

.review-summary {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  text-align: center;
}

.review-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}

.review-tile {
  padding: 12px 14px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid var(--border);
  transition: border-color 0.2s;
}
.review-tile.is-win {
  border-color: rgba(250, 204, 21, 0.5);
  background: rgba(250, 204, 21, 0.06);
}

.review-tile-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.review-tag {
  font-size: 12px;
  font-weight: 700;
  font-family: var(--font-mono);
  padding: 2px 8px;
  border-radius: 99px;
  background: rgba(255, 255, 255, 0.06);
}
.review-tag.up { background: rgba(250, 204, 21, 0.18); color: #fde68a; }
.review-tag.down { color: var(--text-3); }

.review-tile-tickets {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

@media (max-width: 640px) {
  .review-head {
    grid-template-columns: 1fr;
  }
}

/* 本期预测 */
.section-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.section-title h2 {
  font-size: 18px;
  font-weight: 700;
  margin: 0;
}
.see-all {
  font-size: 13px;
  color: var(--text-3);
  text-decoration: none;
  transition: color 0.2s;
}
.see-all:hover { color: var(--text-1); }

.predict-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 14px;
}

.predict-tile {
  padding: 14px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid var(--border);
}

.predict-tile-head {
  margin-bottom: 10px;
}

.predict-tile-tickets {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

/* 原有统计小卡 */
.grid {
  display: grid;
  gap: 16px;
}

.stats-grid {
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.stat-card { padding: 20px; }

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
.model-badge[data-model="xgboost"] { background: rgba(132, 204, 22, 0.2); color: #bef264; }
.model-badge[data-model="lstm"] { background: rgba(236, 72, 153, 0.2); color: #f9a8d4; }
.model-badge[data-model="transformer"] { background: rgba(244, 63, 94, 0.2); color: #fda4af; }
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
  justify-content: space-between;
  gap: 16px;
  padding: 22px 24px;
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

.loading {
  padding: 32px;
  text-align: center;
  color: var(--text-3);
  border: 1px dashed var(--border);
  border-radius: var(--radius-lg);
  background: rgba(255, 255, 255, 0.02);
}
</style>
