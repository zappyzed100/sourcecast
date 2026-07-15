import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./index.css";
import App from "./App.tsx";

const rootElement = document.getElementById("root");
if (rootElement === null) {
	throw new Error("main.tsx: #root 要素が見つからない（index.htmlの構成崩れ）");
}

createRoot(rootElement).render(
	<StrictMode>
		<BrowserRouter>
			<App />
		</BrowserRouter>
	</StrictMode>,
);
