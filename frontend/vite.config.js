import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

/**
 * Vite 配置
 * base 适配 GitHub Pages 子路径部署（例如 username.github.io/DaLeTou/）
 * 通过环境变量 VITE_BASE 覆盖，本地开发默认 "/"
 */
export default defineConfig({
  plugins: [vue()],
  base: process.env.VITE_BASE || "/",
  server: {
    port: 5173,
  },
});
