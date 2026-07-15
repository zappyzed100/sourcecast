// index.ts — Python(Pydantic)から生成するJSON Schema/TypeScript型の公開エントリポイント
//
// Phase 1で `schema/` へJSON Schemaをコミットし、そこから生成した型をここから再輸出する
// （手書きの型で二重管理しない — plan.md §2.3）。

export const CONTRACTS_SCHEMA_VERSION = "unreleased" as const;
