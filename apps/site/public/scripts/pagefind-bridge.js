// pagefind-bridge.js — public/直下の静的ファイル(Viteのビルドグラフ外・手編集の対象)。
//
// index.astro のインラインscriptから動的importする代わりに、この橋渡しファイルを
// <script type="module" src="..."> として実行時にDOM挿入する。理由:
//   1. Viteは検出できたimport()呼び出しをすべて`__vitePreload(factory, __VITE_PRELOAD__)`で
//      ラップするが、ビルドグラフ外のパス(/pagefind/pagefind.js)は`__VITE_PRELOAD__`が
//      解決されず「__VITE_PRELOAD__ is not defined」で例外になる(実機で確認済み)。
//   2. src=での読み込みはCSPのscript-src 'self'でオリジン一致により許可され、
//      new Function()等のeval系(要unsafe-eval)を使わずに済む。
import * as pagefind from "/pagefind/pagefind.js";

window.dispatchEvent(
	new CustomEvent("pagefind-bridge:loaded", { detail: pagefind }),
);
