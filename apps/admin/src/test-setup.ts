// test-setup.ts — Vitestのjsdom環境に@testing-library/jest-domのマッチャーを追加する。
// globals:trueを使っていないため@testing-library/reactの自動cleanupが効かない
// ——各テスト後に明示的にcleanup()する(同じdata-testidを複数テストで使うと
// 前のテストのDOMが残り「複数要素が見つかった」エラーになる)。
import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";

afterEach(() => {
	cleanup();
});
