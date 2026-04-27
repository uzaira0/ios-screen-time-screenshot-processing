import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";
import { ServiceProvider } from "./core";
import { registerServiceWorker, onSWUpdate } from "./lib/serviceWorker";

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("Failed to find the root element");
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <ServiceProvider>
      <App />
    </ServiceProvider>
  </React.StrictMode>,
);

// Register SW after render so it doesn't block first paint.
registerServiceWorker();
onSWUpdate(() => {
  window.location.reload();
});
