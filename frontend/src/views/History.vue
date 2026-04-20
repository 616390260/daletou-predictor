<template>
  <div class="container">
    <div class="page-head">
      <h1>历史开奖</h1>
      <p>近 500 期大乐透真实开奖号码（数据源：中国体育彩票官方 API）</p>
    </div>

    <div class="card" v-if="history.length">
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>期号</th>
              <th>日期</th>
              <th>号码</th>
              <th class="num">销量</th>
              <th class="num">奖池</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in visibleRows" :key="row.issue">
              <td class="mono">{{ row.issue }}</td>
              <td class="mono">{{ row.date }}</td>
              <td><BallRow :front="row.front" :back="row.back" sm /></td>
              <td class="num mono">{{ fmt(row.sales) }}</td>
              <td class="num mono">{{ fmt(row.pool) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="pager" v-if="history.length > pageSize">
        <button class="btn" :disabled="page <= 1" @click="page--">上一页</button>
        <span class="page-info">第 {{ page }} / {{ totalPages }} 页</span>
        <button class="btn" :disabled="page >= totalPages" @click="page++">下一页</button>
      </div>
    </div>

    <div v-else class="loading">加载中…</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { api } from "../api";
import BallRow from "../components/BallRow.vue";

const history = ref([]);
const page = ref(1);
const pageSize = 30;

const totalPages = computed(() => Math.max(1, Math.ceil(history.value.length / pageSize)));
const visibleRows = computed(() => {
  const start = (page.value - 1) * pageSize;
  return history.value.slice(start, start + pageSize);
});

function fmt(n) {
  if (!n) return "—";
  if (n >= 1e8) return (n / 1e8).toFixed(2) + " 亿";
  if (n >= 1e4) return (n / 1e4).toFixed(2) + " 万";
  return String(n);
}

onMounted(async () => {
  history.value = (await api.history()) || [];
});
</script>

<style scoped>
.page-head {
  margin-bottom: 24px;
}

.page-head h1 {
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.page-head p {
  color: var(--text-3);
  font-size: 14px;
  margin-top: 4px;
}

.table-wrap {
  overflow-x: auto;
}

.mono {
  font-family: var(--font-mono);
  font-size: 13px;
}

.num {
  text-align: right;
}

.pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding-top: 16px;
  margin-top: 8px;
  border-top: 1px solid var(--border);
}

.pager .btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.page-info {
  font-size: 13px;
  color: var(--text-2);
  font-family: var(--font-mono);
}
</style>
