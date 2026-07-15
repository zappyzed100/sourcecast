// useAsync.ts — API呼び出し1本の読み込み状態を管理する小さなフック。
// loading/error/successの3状態のみを持ち、空データはsuccess側で呼び出し元がUI分岐する。
import { useEffect, useState } from "react";

export type AsyncState<T> =
	| { status: "loading" }
	| { status: "error"; error: unknown }
	| { status: "success"; data: T };

export function useAsync<T>(
	fetcher: () => Promise<T>,
	deps: readonly unknown[] = [],
): AsyncState<T> {
	const [state, setState] = useState<AsyncState<T>>({ status: "loading" });

	useEffect(() => {
		let cancelled = false;
		setState({ status: "loading" });
		fetcher()
			.then((data) => {
				if (!cancelled) setState({ status: "success", data });
			})
			.catch((error: unknown) => {
				if (!cancelled) setState({ status: "error", error });
			});
		return () => {
			cancelled = true;
		};
		// biome-ignore lint/correctness/useExhaustiveDependencies: depsは呼び出し側が明示的に渡す再取得トリガーの引数そのもの(汎用フックのため配列リテラルにできない)
	}, deps);

	return state;
}
