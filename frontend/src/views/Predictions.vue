<template>
  <div class="container">
    <div class="page-head">
      <h1>预测记录</h1>
      <p>每期每个模型给出 1 注投注。绿圈 = 命中号码，未开奖期标记为"待开奖"。</p>
    </div>

    <section v-if="laya" class="card laya-overview" aria-labelledby="laya-title">
      <h2 id="laya-title">Laya 独立决策 · 实验中</h2>
      <dl class="laya-facts">
        <div>
          <dt>可信历史样本</dt>
          <dd>{{ laya.dataset?.issues ?? "—" }} 期 / {{ laya.dataset?.tickets ?? "—" }} 候选</dd>
        </div>
        <div>
          <dt>冻结测试</dt>
          <dd>{{ laya.evaluation?.issues ?? "—" }} 期</dd>
        </div>
        <div>
          <dt>部署版本训练到</dt>
          <dd>{{ laya.active_model?.trained_through_issue || laya.trained_through_issue || "—" }} 期</dd>
        </div>
      </dl>
      <p class="laya-note">评分不是可靠中奖概率，尚未参与原模型集成。历史选择按回测评审展示，不代表当时已发布预测。</p>
    </section>

    <div v-if="!items.length" class="loading">加载中…</div>

    <div v-else class="list">
      <article v-for="item in displayedItems" :key="item.issue" class="card issue-card">
        <header class="issue-head">
          <div>
            <div class="issue-title">
              <span class="issue-num">第 {{ item.issue }} 期</span>
              <span class="tag" v-if="item.real">已开奖 · {{ item.real.date }}</span>
              <span class="tag tag-primary" v-else>待开奖</span>
            </div>
            <div v-if="item.real" class="real-row">
              <span class="real-label">真实开奖</span>
              <BallRow :front="item.real.front" :back="item.real.back" size="sm" />
            </div>
          </div>
        </header>

        <div class="models">
          <div v-for="m in item.models" :key="m.model" class="model-block">
            <div class="model-head">
              <span class="model-badge" :data-model="m.model">{{ m.label }}</span>
              <span class="model-stat" v-if="hasHit(m)">{{ summary(m) }}</span>
            </div>
            <div class="tickets">
              <div v-for="t in m.tickets" :key="t.idx" class="ticket">
                <span class="ticket-idx">#{{ t.idx + 1 }}</span>
                <BallRow
                  :front="t.front"
                  :back="t.back"
                  :hit-front="item.real?.front || []"
                  :hit-back="item.real?.back || []"
                  size="sm"
                />
                <span v-if="t.result" class="result" :class="{ win: t.result.amount > 0 }">
                  {{ t.result.level || "未中奖" }}
                  <em v-if="t.result.amount > 0">+¥{{ fmtMoney(t.result.amount) }}</em>
                </span>
              </div>
            </div>
          </div>
        </div>

        <section v-if="item.layaDecision" class="laya-decision" :aria-label="`第 ${item.issue} 期 Laya 独立决策`">
          <div class="laya-decision-head">
            <h2>Laya 独立决策</h2>
            <span class="tag">{{ decisionKind(item.layaDecision.kind) }}</span>
          </div>
          <div class="laya-selection">
            <span>选自</span>
            <span class="model-badge" :data-model="item.layaDecision.selected_model">
              {{ item.layaDecision.label || item.layaDecision.selected_model || "未知模型" }}
            </span>
            <span class="laya-score">模型评分 {{ fmtScore(item.layaDecision.score) }}</span>
          </div>
          <div class="ticket laya-ticket">
            <BallRow
              :front="item.layaDecision.front || []"
              :back="item.layaDecision.back || []"
              :hit-front="item.real?.front || []"
              :hit-back="item.real?.back || []"
              size="sm"
            />
            <span v-if="item.layaDecision.result" class="result" :class="{ win: item.layaDecision.result.amount > 0 }">
              前区 {{ fmtHits(item.layaDecision.result.front_hit) }} / 后区 {{ fmtHits(item.layaDecision.result.back_hit) }} 命中 ·
              {{ item.layaDecision.result.level || "未中奖" }}
              <em v-if="item.layaDecision.result.amount > 0">+¥{{ fmtMoney(item.layaDecision.result.amount) }}</em>
            </span>
          </div>
          <p class="laya-note laya-version">
            训练截止 {{ item.layaDecision.trained_through_issue || "—" }} 期 · 版本 {{ item.layaDecision.model_version || "—" }}
          </p>
          <p class="laya-note">模型评分仅用于比较候选，不代表中奖概率。</p>
        </section>
      </article>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from "vue";
import { api } from "../api";
import BallRow from "../components/BallRow.vue";

const items = ref([]);
const laya = ref(null);
const displayedItems = computed(() => {
  const decisions = new Map(
    (Array.isArray(laya.value?.decisions) ? laya.value.decisions : [])
      .filter((decision) => decision?.issue)
      .map((decision) => [String(decision.issue), decision]),
  );
  return items.value.map((item) => ({
    ...item,
    layaDecision: decisions.get(String(item.issue)),
  }));
});

function decisionKind(kind) {
  return {
    heldout: "冻结回测选择",
    prospective: "本期独立选择",
    retrospective: "历史评审",
  }[kind] || "实验选择";
}

function fmtScore(score) {
  return Number.isFinite(score) && score >= 0 && score <= 1
    ? `${(score * 100).toFixed(1)}%`
    : "—";
}

function fmtHits(hits) {
  return Number.isInteger(hits) && hits >= 0 ? hits : "—";
}

function hasHit(m) {
  return m.tickets.some((t) => t.result && t.result.amount > 0);
}

function summary(m) {
  const wins = m.tickets.filter((t) => t.result && t.result.amount > 0).length;
  const total = m.tickets.reduce((s, t) => s + (t.result?.amount || 0), 0);
  return `${wins}/${m.tickets.length} 中奖 · 共 ¥${fmtMoney(total)}`;
}

function fmtMoney(n) {
  if (!n) return "0";
  if (n >= 1e4) return (n / 1e4).toFixed(2) + "万";
  return n.toLocaleString();
}

onMounted(async () => {
  await Promise.all([
    api.predictions().then((data) => { items.value = data || []; }),
    api.laya().then((data) => { laya.value = data; }),
  ]);
});
</script>

<style scoped>
.page-head h1 {
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.page-head p {
  color: var(--text-3);
  font-size: 14px;
  margin-top: 4px;
  margin-bottom: 24px;
}

.list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.laya-overview {
  margin-bottom: 24px;
}

.laya-overview h2,
.laya-decision h2 {
  font-size: 15px;
  font-weight: 600;
}

.laya-facts {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 28px;
  margin: 12px 0;
  font-size: 13px;
}

.laya-facts dt,
.laya-note,
.laya-selection {
  color: var(--text-2);
}

.laya-facts dd {
  margin-top: 2px;
  font-family: var(--font-mono);
}

.laya-note {
  font-size: 12px;
  max-width: 75ch;
  overflow-wrap: anywhere;
}

.laya-decision {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
  min-width: 0;
}

.laya-decision-head,
.laya-selection {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.laya-selection {
  font-size: 12px;
  margin: 10px 0;
}

.laya-score {
  font-family: var(--font-mono);
}

.laya-ticket {
  margin-bottom: 10px;
}

.laya-ticket .result {
  color: var(--text-2);
}

.laya-ticket .result.win {
  color: var(--green);
}

.laya-version {
  margin-bottom: 4px;
}

.issue-card {
  padding: 20px 24px;
}

.issue-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 16px;
}

.issue-title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.issue-num {
  font-size: 17px;
  font-weight: 700;
  font-family: var(--font-mono);
}

.real-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.real-label {
  font-size: 12px;
  color: var(--text-3);
  font-family: var(--font-mono);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.models {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 12px;
}

.model-block {
  padding: 14px 16px;
  border-radius: var(--radius-md);
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border);
}

.model-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.model-badge {
  font-size: 12px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.06);
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

.model-stat {
  font-size: 11px;
  color: var(--green);
  font-family: var(--font-mono);
}

.tickets {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ticket {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.ticket-idx {
  font-size: 11px;
  color: var(--text-3);
  font-family: var(--font-mono);
  width: 24px;
  flex-shrink: 0;
}

.result {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-3);
  font-family: var(--font-mono);
}

.result.win {
  color: var(--green);
}

.result em {
  font-style: normal;
  margin-left: 4px;
}

@media (max-width: 600px) {
  .models {
    grid-template-columns: minmax(0, 1fr);
  }

  .issue-card {
    padding: 16px;
  }

  .issue-title,
  .real-row {
    flex-wrap: wrap;
  }

  .laya-ticket .result {
    margin-left: 0;
    width: 100%;
  }
}
</style>
