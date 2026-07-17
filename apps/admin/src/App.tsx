import { NavLink, Route, Routes } from "react-router-dom";
import { Candidates } from "./pages/Candidates";
import { Dashboard } from "./pages/Dashboard";
import { Episodes } from "./pages/Episodes";
import { Jobs } from "./pages/Jobs";

function App() {
	return (
		<>
			<header>
				<h1>history-radio 管理画面</h1>
				<nav aria-label="管理画面ナビゲーション">
					<NavLink to="/" end>
						ダッシュボード
					</NavLink>
					<NavLink to="/candidates">候補一覧</NavLink>
					<NavLink to="/episodes">エピソード</NavLink>
					<NavLink to="/jobs">ジョブ</NavLink>
				</nav>
			</header>
			<main>
				<Routes>
					<Route path="/" element={<Dashboard />} />
					<Route path="/candidates" element={<Candidates />} />
					<Route path="/episodes" element={<Episodes />} />
					<Route path="/jobs" element={<Jobs />} />
				</Routes>
			</main>
		</>
	);
}

export default App;
