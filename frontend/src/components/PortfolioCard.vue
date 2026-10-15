<template>
  <section class="card coverage-card" aria-labelledby="portfolio-title">
    <div class="portfolio-heading">
      <h2 id="portfolio-title">第 {{ issue }} 期 · 九注覆盖方案</h2>
      <span class="budget">9 注 · ¥18</span>
    </div>
    <template v-if="current">
      <p class="explanation">保留九模型前区，调整后区以减少中奖覆盖重叠。与原九注分别比较，每套预算均为 18 元。</p>
      <dl class="coverage-metrics">
        <div><dt>原九注理论覆盖</dt><dd>{{ percent(current.original_count / current.total_draws) }}</dd></div>
        <div><dt>覆盖方案理论覆盖</dt><dd>{{ percent(current.optimized_count / current.total_draws) }}</dd></div>
        <div><dt>覆盖增加</dt><dd>+{{ ((current.optimized_count - current.original_count) / current.total_draws * 100).toFixed(2) }}<small> 个百分点</small></dd></div>
      </dl>
      <p class="explanation">指均匀随机开奖下“至少一注中任意奖”的精确概率，包含 5 元等小奖；不是回本或盈利概率。没有证据表明单注预测能力因此提高。</p>
      <div class="portfolio-tickets">
        <div v-for="(ticket, index) in current.tickets" :key="index" class="portfolio-ticket">
          <span class="ticket-label">{{ index + 1 }} · {{ MODEL_LABELS[ticket.model] || ticket.model }}</span>
          <BallRow :front="ticket.front" :back="ticket.back" size="sm" />
        </div>
      </div>
      <p class="explanation">前区候选截止 {{ current.history_cutoff }} 期 · 方案生成于 {{ formatDate(current.created_at) }} · 开奖后自动核对</p>
    </template>
    <p v-else class="explanation" role="status">{{ loaded ? '本期覆盖方案尚未生成或暂时无法加载，原九模型预测仍可查看。' : '正在加载本期覆盖方案…' }}</p>

    <template v-if="report?.summary">
      <div class="comparison-wrap">
        <table class="table comparison">
          <caption>同预算核对 · 至少一注中奖的期数</caption>
          <thead><tr><th>记录类型</th><th class="num">原九注</th><th class="num">覆盖方案</th></tr></thead>
          <tbody>
            <tr v-for="group in groups" :key="group.key">
              <td>{{ group.label }}<small v-if="group.stat?.periods">{{ group.stat.first_issue }}—{{ group.stat.last_issue }} · {{ group.stat.periods }} 期</small></td>
              <td class="num">{{ count(group.stat, 'original_wins') }}</td>
              <td class="num">{{ count(group.stat, 'optimized_wins') }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="explanation">历史方案是在开奖后对已核验候选做的探索性模拟，不能当作提前发布的预测。前瞻核对仅统计本方案实际在开奖前存档的期数；中奖次数不代表盈利。</p>
      <details v-if="settled.length" class="portfolio-history">
        <summary>逐期查看 {{ settled.length }} 期核对</summary>
        <div class="comparison-wrap">
          <table class="table">
            <thead><tr><th>期号 / 类型</th><th class="num">原九注中奖</th><th class="num">覆盖方案中奖</th></tr></thead>
            <tbody><tr v-for="run in settled" :key="`${run.issue}-${run.version}`">
              <td>{{ run.issue }} · {{ run.kind === 'prospective' ? '前瞻' : '模拟' }}</td>
              <td class="num">{{ run.result.original.winning_tickets }} / 9</td>
              <td class="num">{{ run.result.optimized.winning_tickets }} / 9</td>
            </tr></tbody>
          </table>
        </div>
      </details>
    </template>
  </section>
</template>

<script setup>
import { computed } from 'vue';
import BallRow from './BallRow.vue';
import { MODEL_LABELS } from '../api/models';
import { currentPortfolio } from '../utils/portfolio';

const props = defineProps({ report: Object, issue: String, loaded: Boolean });
const current = computed(() => currentPortfolio(props.report, props.issue));
const groups = computed(() => [
  { key: 'historical_simulation', label: '历史模拟', stat: props.report?.summary?.historical_simulation },
  { key: 'prospective', label: '前瞻核对', stat: props.report?.summary?.prospective },
]);
const settled = computed(() => (props.report?.runs || []).filter((r) => r.result && r.version === props.report.version));
const percent = (n) => `${(n * 100).toFixed(2)}%`;
const count = (s, key) => s?.periods ? `${s[key]} / ${s.periods}` : '待开奖积累';
const formatDate = (date) => new Date(date).toLocaleString('zh-CN', { hour12: false });
</script>

<style scoped>
.coverage-card { min-width: 0; }
.portfolio-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
h2 { margin: 0; font-size: 18px; }
.budget { font-family: var(--font-mono); font-size: 14px; color: var(--text-1); }
.explanation { color: var(--text-2); font-size: 13px; line-height: 1.75; margin: 14px 0; max-width: 75ch; }
.coverage-metrics { display: flex; flex-wrap: wrap; gap: 20px 36px; padding: 18px 0; margin: 0; border-block: 1px solid var(--border); }
dt { font-size: 12px; color: var(--text-2); margin-bottom: 8px; }
dd { margin: 0; font-size: 26px; font-weight: 700; font-family: var(--font-mono); }
dd small { font-size: 12px; font-weight: 400; }
.portfolio-tickets { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr)); gap: 18px 24px; margin-top: 22px; }
.portfolio-ticket { min-width: 0; }
.ticket-label { display: block; color: var(--text-2); font-size: 12px; margin-bottom: 8px; }
.comparison-wrap { overflow-x: auto; margin-top: 20px; }
.comparison caption { text-align: left; color: var(--text-1); font-weight: 600; padding-bottom: 12px; }
td small { display: block; font-size: 11px; color: var(--text-2); margin-top: 4px; }
th, td { white-space: nowrap; }
.portfolio-history summary { cursor: pointer; color: var(--text-2); font-size: 13px; }
.portfolio-history summary:focus-visible { outline: 2px solid var(--blue); outline-offset: 4px; }
@media (max-width: 600px) { .coverage-metrics { gap: 18px 24px; } dd { font-size: 24px; } }
</style>
