<template>
  <div v-if="draws.length" class="number-trend">
    <p class="trend-caption">从左到右为过去 {{ draws.length }} 期。● 表示出现，· 表示未出现；仅展示 {{ decision.issue }} 期之前的开奖。</p>
    <div class="trend-scroll" tabindex="0" role="region" aria-label="候选号码历史走势，可横向滚动">
      <table>
        <caption class="sr-only">Laya 入选号码的历史出现次数和遗漏期数</caption>
        <thead><tr><th scope="col">候选号码</th><th v-for="draw in draws" :key="draw.issue" scope="col">{{ String(draw.issue).slice(-3) }}</th><th scope="col">出现 / 遗漏</th></tr></thead>
        <tbody>
          <tr v-for="row in rows" :key="`${row.zone}-${row.number}`" :class="row.zone">
            <th scope="row">{{ row.zone === 'front' ? '前' : '后' }} {{ String(row.number).padStart(2, '0') }}</th>
            <td v-for="(present, index) in row.present" :key="draws[index].issue" :class="{ present }"
                :title="`${draws[index].issue} 期：${present ? '出现' : '未出现'}`">{{ present ? '●' : '·' }}</td>
            <td class="trend-count">{{ row.count }} 次 / {{ row.omission }} 期</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="trend-caption">同源开奖数据已用于频率、遗漏和转移等数值特征。历史走势不等于下一期中奖概率。</p>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { trendHistory, trendRows } from "../utils/numberTrend";
const props = defineProps({ history: { type: Array, default: () => [] }, decision: { type: Object, required: true } });
const draws = computed(() => trendHistory(props.history, props.decision.issue));
const rows = computed(() => trendRows(draws.value, props.decision));
</script>

<style scoped>
.trend-scroll { overflow-x: auto; max-width: 100%; }
.trend-scroll:focus-visible { outline: 2px solid var(--blue); outline-offset: 3px; }
table { width: 100%; border-collapse: collapse; font-size: 12px; white-space: nowrap; }
th, td { min-width: 25px; height: 28px; text-align: center; border-bottom: 1px solid var(--border); }
th { font-weight: 500; color: var(--text-2); padding: 0 4px; }
td { color: var(--text-3); }
.front .present { color: #fb7185; background: rgba(244, 63, 94, .12); }
.back .present { color: #60a5fa; background: rgba(59, 130, 246, .12); }
.trend-count { color: var(--text-2); padding: 0 8px; }
.trend-caption { color: var(--text-2); font-size: 12px; line-height: 1.6; margin: 12px 0; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
</style>
