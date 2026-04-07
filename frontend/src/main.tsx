import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";
import { ServiceProvider } from "./core";

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
