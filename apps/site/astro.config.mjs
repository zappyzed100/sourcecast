// @ts-check
import { defineConfig } from "astro/config";

// https://astro.build/config
export default defineConfig({
	// 本番ドメイン(2026-07-19確定)。未設定だとcontext.siteがundefinedになり、
	// RSSのlink/enclosure/itunes:image等が全てhttps://example.invalid/という
	// ダミーURLのまま公開されてしまう(実際に発覚した不具合——feed.xmlの絶対URL生成は
	// すべてこの値に依存する)。
	site: "https://itsuwawa.com",
	// インラインscript/styleへハッシュを自動付与し、'unsafe-inline'無しでCSPを成立させる
	// (plan.md §3.4)。static出力なので<meta http-equiv>として出力される
	// (Cloudflare Pagesのレスポンスヘッダーはpublic/_headersで別途設定する)。
	security: {
		csp: true,
	},
	vite: {
		build: {
			// falseにするとVite独自のモジュールプリロードヘルパー(`__VITE_PRELOAD__`参照)を
			// 挿入しなくなる。ビルドグラフ外の /pagefind/pagefind.js を動的importする際に
			// ヘルパーが機能せず例外になっていたため無効化する(実機で確認済み)。
			modulePreload: false,
		},
	},
});
