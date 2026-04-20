<template>
  <footer class="footer">
    <div class="container inner">
      <div>
        <b>大乐透预测实验室</b> · 用数据说话
      </div>
      <div class="meta" v-if="meta">
        <span>数据更新：{{ meta.generated_at }}</span>
        <span>·</span>
        <span>最新期号：{{ meta.latest_issue || "—" }}</span>
      </div>
      <div class="disclaimer">
        本站仅用于算法研究与彩票随机性验证，不构成任何投注建议。<br />
        理性购彩，适度娱乐。
      </div>
    </div>
  </footer>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { api } from "../api";

const meta = ref(null);

onMounted(async () => {
  meta.value = await api.meta();
});
</script>

<style scoped>
.footer {
  padding: 32px 0;
  border-top: 1px solid var(--border);
  background: rgba(0, 0, 0, 0.3);
  color: var(--text-3);
  font-size: 13px;
}

.inner {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
  text-align: center;
}

.inner > div:first-child b {
  color: var(--text-1);
}

.meta {
  display: flex;
  gap: 10px;
  font-family: var(--font-mono);
  font-size: 12px;
}

.disclaimer {
  margin-top: 12px;
  font-size: 12px;
  line-height: 1.6;
}
</style>
