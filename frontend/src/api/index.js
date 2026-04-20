/**
 * 前端数据访问层
 * 所有数据读自 public/data/*.json（由后端脚本生成、GitHub Actions 定时更新）
 */

const BASE = `${import.meta.env.BASE_URL}data`;

async function fetchJson(name, fallback = null) {
  try {
    const res = await fetch(`${BASE}/${name}?t=${Date.now()}`);
    if (!res.ok) throw new Error(res.statusText);
    return await res.json();
  } catch (err) {
    console.warn(`[api] load ${name} failed:`, err.message);
    return fallback;
  }
}

export const api = {
  meta: () => fetchJson("meta.json", null),
  history: () => fetchJson("history.json", []),
  frequency: () => fetchJson("frequency.json", null),
  predictions: () => fetchJson("predictions.json", []),
  stats: () => fetchJson("stats.json", { summary: [], trend: {} }),
};
