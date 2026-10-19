<template>
  <section class="card retrained-comparison" aria-labelledby="retrained-title">
    <header class="comparison-head">
      <h2 id="retrained-title">{{ report.issue }} 重训对照 <span>· 事后重算</span></h2>
      <p>训练截止 {{ report.trained_through_issue }} 期 · 不计入开奖前成绩 · 原预测未覆盖</p>
    </header>

    <div class="comparison-real">
      <span>真实开奖 <time :datetime="report.real.date">{{ report.real.date }}</time></span>
      <BallRow :front="report.real.front" :back="report.real.back" size="sm" />
    </div>

    <div class="comparison-summary" aria-label="原预测与重训结果汇总">
      <div v-for="(label, key) in variants" :key="key" class="summary-side">
        <h3>{{ label }}</h3>
        <dl>
          <div><dt>投注</dt><dd>{{ report.summary[key].tickets }} 注 · ¥{{ report.summary[key].cost }}</dd></div>
          <div><dt>中奖注数</dt><dd>{{ report.summary[key].winning_tickets }} / {{ report.summary[key].tickets }}</dd></div>
          <div><dt>奖金估算</dt><dd>¥{{ report.summary[key].estimated_prize }}</dd></div>
        </dl>
      </div>
    </div>

    <div class="comparison-columns" aria-hidden="true">
      <span>模型</span><span>原预测</span><span>重训重算</span>
    </div>
    <div class="comparison-models">
      <div v-for="row in report.models" :key="row.model" class="comparison-model">
        <div class="comparison-model-name">
          <h3><span class="model-badge" :data-model="row.model">{{ row.label }}</span></h3>
          <span class="change-note">{{ row.changed ? "号码有变化" : "号码相同" }}</span>
        </div>
        <div v-for="(label, key) in variants" :key="key" class="comparison-ticket">
          <span class="ticket-label">{{ label }}</span>
          <BallRow
            :front="row[key].front"
            :back="row[key].back"
            :hit-front="report.real.front"
            :hit-back="report.real.back"
            size="sm"
          />
          <p class="ticket-result" :class="{ win: row[key].result.won }">
            前区 {{ row[key].result.front_hit }} / 后区 {{ row[key].result.back_hit }} 命中 ·
            {{ row[key].result.level || "未中奖" }}
            <span v-if="row[key].result.amount > 0"> · 估算 ¥{{ row[key].result.amount }}</span>
          </p>
        </div>
      </div>
    </div>
    <p class="comparison-note">绿圈表示命中。奖金为规则估算；本次单期对照不能证明模型预测能力提高。</p>
  </section>
</template>

<script setup>
import BallRow from "./BallRow.vue";

defineProps({ report: { type: Object, required: true } });
const variants = { original: "原预测", retrained: "重训重算" };
</script>

<style scoped>
.retrained-comparison {
  min-width: 0;
  margin-bottom: 24px;
}

.comparison-head h2 {
  font-size: 20px;
  font-weight: 700;
  text-wrap: balance;
}

.comparison-head h2 span {
  color: var(--yellow);
}

.comparison-head p,
.comparison-note {
  color: var(--text-2);
  font-size: 12px;
  margin-top: 8px;
  max-width: 75ch;
}

.comparison-real {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 20px;
  margin: 20px 0;
}

.comparison-real > span {
  font-size: 13px;
  color: var(--text-2);
}

.comparison-real time {
  margin-left: 8px;
  font-family: var(--font-mono);
}

.comparison-summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 24px;
  padding: 16px 0 20px;
  border-top: 1px solid var(--border);
}

.summary-side h3 {
  font-size: 14px;
  margin-bottom: 10px;
}

.summary-side dl {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 28px;
  font-size: 13px;
}

.summary-side dt {
  color: var(--text-2);
  font-size: 12px;
}

.summary-side dd {
  margin-top: 2px;
  font-family: var(--font-mono);
}

.comparison-columns,
.comparison-model {
  display: grid;
  grid-template-columns: 160px repeat(2, minmax(0, 1fr));
  gap: 20px;
}

.comparison-columns {
  padding: 10px 0;
  color: var(--text-2);
  font-size: 12px;
  border-bottom: 1px solid var(--border-strong);
}

.comparison-model {
  padding: 16px 0;
  border-bottom: 1px solid var(--border);
}

.comparison-model h3 {
  font-size: 12px;
  line-height: 1.8;
}

.comparison-ticket,
.comparison-model-name {
  min-width: 0;
}

.change-note {
  display: block;
  color: var(--text-2);
  font-size: 11px;
  margin-top: 6px;
}

.ticket-label {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.ticket-result {
  color: var(--text-2);
  font-size: 12px;
  margin-top: 8px;
}

.ticket-result.win {
  color: #6ee7b7;
}

.comparison-note {
  margin-top: 16px;
}

@media (max-width: 900px) {
  .comparison-model {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 14px 20px;
  }

  .comparison-model-name {
    grid-column: 1 / -1;
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
  }

  .change-note {
    margin-top: 0;
  }

  .comparison-columns {
    display: none;
  }

  .ticket-label {
    position: static;
    display: block;
    width: auto;
    height: auto;
    clip-path: none;
    white-space: normal;
    font-size: 12px;
    color: var(--text-2);
    margin-bottom: 8px;
  }
}

@media (max-width: 600px) {
  .retrained-comparison {
    padding: 16px;
  }

  .comparison-head h2 {
    font-size: 18px;
  }

  .comparison-summary {
    grid-template-columns: minmax(0, 1fr);
    gap: 16px;
  }

  .comparison-model {
    grid-template-columns: minmax(0, 1fr);
    gap: 16px;
  }
}
</style>
