<template>
  <div class="container">
    <div class="page-head">
      <h1>历史开奖</h1>
      <p>
        共收录 <b>{{ history.length }}</b> 期大乐透真实开奖号码 · 2007-05-30 至今 · 数据源：中国体育彩票官方 API · 每期自动更新
      </p>
    </div>

    <div v-if="!history.length" class="empty-state">
      <div class="empty-icon">⏳</div>
      <div class="empty-title">正在加载数据…</div>
    </div>

    <template v-else>
      <!-- 工具条 -->
      <div class="toolbar card">
        <div class="tool-item">
          <label>搜索期号</label>
          <input
            v-model.trim="keyword"
            type="search"
            class="input"
            placeholder="如 26042"
            @input="page = 1"
          />
        </div>

        <div class="tool-item">
          <label>年份</label>
          <select v-model="yearFilter" class="select" @change="page = 1">
            <option value="">全部年份</option>
            <option v-for="y in yearOptions" :key="y" :value="y">{{ y }}</option>
          </select>
        </div>

        <div class="tool-item">
          <label>每页</label>
          <select v-model.number="pageSize" class="select" @change="page = 1">
            <option :value="20">20 条</option>
            <option :value="50">50 条</option>
            <option :value="100">100 条</option>
            <option :value="200">200 条</option>
          </select>
        </div>

        <div class="tool-spacer" />

        <div class="tool-stat">
          筛选后：<b>{{ filtered.length }}</b> 期
        </div>
      </div>

      <!-- 无筛选结果 -->
      <div v-if="!filtered.length" class="empty-state small">
        <div class="empty-icon">🔍</div>
        <div class="empty-title">没有匹配的期号</div>
        <div class="empty-desc">试着清空筛选条件或换一个关键词。</div>
      </div>

      <div v-else class="card">
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
                <td><BallRow :front="row.front" :back="row.back" size="sm" /></td>
                <td class="num mono">{{ fmt(row.sales) }}</td>
                <td class="num mono">{{ fmt(row.pool) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="pager" v-if="totalPages > 1">
          <button class="btn" :disabled="page <= 1" @click="page = 1">« 首页</button>
          <button class="btn" :disabled="page <= 1" @click="page--">上一页</button>
          <span class="page-info">第 {{ page }} / {{ totalPages }} 页</span>
          <button class="btn" :disabled="page >= totalPages" @click="page++">下一页</button>
          <button class="btn" :disabled="page >= totalPages" @click="page = totalPages">末页 »</button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { api } from "../api";
import BallRow from "../components/BallRow.vue";

const history = ref([]);
const page = ref(1);
const pageSize = ref(50);
const keyword = ref("");
const yearFilter = ref("");

/**
 * 年份下拉选项（从数据 date 里提取）
 */
const yearOptions = computed(() => {
  const set = new Set();
  history.value.forEach((r) => {
    if (r.date) set.add(r.date.slice(0, 4));
  });
  return [...set].sort().reverse();
});

/**
 * 按关键词、年份筛选
 */
const filtered = computed(() => {
  const kw = keyword.value.trim();
  const y = yearFilter.value;
  if (!kw && !y) return history.value;
  return history.value.filter((r) => {
    if (kw && !r.issue.includes(kw)) return false;
    if (y && (!r.date || !r.date.startsWith(y))) return false;
    return true;
  });
});

const totalPages = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize.value)));

const visibleRows = computed(() => {
  const start = (page.value - 1) * pageSize.value;
  return filtered.value.slice(start, start + pageSize.value);
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
.page-head p b {
  color: var(--text-1);
  font-family: var(--font-mono);
}

.toolbar {
  display: flex;
  gap: 16px;
  align-items: flex-end;
  flex-wrap: wrap;
  padding: 16px;
  margin-bottom: 16px;
}

.tool-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 120px;
}
.tool-item label {
  font-size: 11px;
  color: var(--text-3);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.input, .select {
  padding: 8px 10px;
  font-size: 13px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text-1);
  font-family: var(--font-mono);
}
.input:focus, .select:focus {
  outline: none;
  border-color: var(--border-strong);
  background: rgba(255, 255, 255, 0.06);
}

.tool-spacer { flex: 1; }

.tool-stat {
  font-size: 13px;
  color: var(--text-2);
}
.tool-stat b {
  color: var(--text-1);
  font-family: var(--font-mono);
  font-weight: 700;
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
  gap: 10px;
  padding-top: 16px;
  margin-top: 8px;
  border-top: 1px solid var(--border);
  flex-wrap: wrap;
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

.empty-state {
  padding: 64px 24px;
  text-align: center;
  border: 1px dashed var(--border);
  border-radius: var(--radius-lg);
  background: rgba(255, 255, 255, 0.015);
}
.empty-state.small { padding: 32px 24px; }
.empty-icon { font-size: 44px; margin-bottom: 12px; opacity: 0.9; }
.empty-title { font-size: 18px; font-weight: 700; color: var(--text-1); margin-bottom: 8px; }
.empty-desc { font-size: 13px; color: var(--text-3); line-height: 1.7; }
</style>
