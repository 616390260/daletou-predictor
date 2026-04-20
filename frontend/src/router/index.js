import { createRouter, createWebHashHistory } from "vue-router";
import Home from "../views/Home.vue";
import History from "../views/History.vue";
import Predictions from "../views/Predictions.vue";
import ModelCompare from "../views/ModelCompare.vue";
import About from "../views/About.vue";

/**
 * 使用 Hash 路由以兼容 GitHub Pages 子路径部署
 */
const routes = [
  { path: "/", name: "home", component: Home, meta: { title: "首页" } },
  { path: "/history", name: "history", component: History, meta: { title: "历史开奖" } },
  { path: "/predictions", name: "predictions", component: Predictions, meta: { title: "预测记录" } },
  { path: "/compare", name: "compare", component: ModelCompare, meta: { title: "模型对比" } },
  { path: "/about", name: "about", component: About, meta: { title: "关于" } },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

export default router;
