import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // The API only allows the origin http://localhost:5173 (CORS): fail loudly
  // instead of silently moving to 5174 if the port is taken.
  server: { port: 5173, strictPort: true },
  test: {
    // A pretend browser, so a component can be rendered and clicked without one.
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/setupTests.ts",
    // Nothing here is allowed to reach the network. Every test says what the API
    // answers, so a failure is always about this code and never about the shop
    // being up, or slow, or full of somebody else's data.
    restoreMocks: true,
  },
});
