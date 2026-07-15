## ハマりどころ: このパッケージだけ TypeScript 6.x に固定している

リポジトリ全体の方針(plan.md §1.2)は TypeScript 7.0.x 固定だが、`astro check` の
実体である `@astrojs/language-server` は TypeScript 7 系がまだ Program 構築の
プログラマティック API を公開していないため動かない(2026-07時点。upstream: astro
roadmap discussion #1321)。このパッケージ(`apps/site`)だけ `typescript@6.0.3` に
固定し、`pnpm --filter apps-site run typecheck` は `astro check` を使う。Astro が
TS7 に対応したらここも7系へ揃えてこのメモを消す。

## Development

When starting the dev server, use background mode:

```
astro dev --background
```

Manage the background server with `astro dev stop`, `astro dev status`, and `astro dev logs`.

## Documentation

Full documentation: https://docs.astro.build

Consult these guides before working on related tasks:

- [Adding pages, dynamic routes, or middleware](https://docs.astro.build/en/guides/routing/)
- [Working with Astro components](https://docs.astro.build/en/basics/astro-components/)
- [Using React, Vue, Svelte, or other framework components](https://docs.astro.build/en/guides/framework-components/)
- [Adding or managing content](https://docs.astro.build/en/guides/content-collections/)
- [Adding styles or using Tailwind](https://docs.astro.build/en/guides/styling/)
- [Supporting multiple languages](https://docs.astro.build/en/guides/internationalization/)
