import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// Settings come from frontend/.env (template: .env.example). Dev: /api is forwarded to the FastAPI server.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  return {
    plugins: [react()],
    server: {
      port: Number(env.VITE_DEV_PORT || 5173),
      proxy: { "/api": env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000" },
    },
  };
});
