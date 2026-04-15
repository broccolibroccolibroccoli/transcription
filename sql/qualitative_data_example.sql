-- 参考: シンプルな定性データ1テーブル（ファイル紐付けなしの最小例）
-- アプリ本番は transcript_vector_chunks を使用します。

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS public.qualitative_data (
    id SERIAL PRIMARY KEY,
    content TEXT,
    embedding VECTOR(1536)
);

-- 登録例（アプリは psycopg から embedding 列へ文字列を %s::vector で渡す）
-- INSERT INTO public.qualitative_data (content, embedding)
-- VALUES ('分割したテキスト...', '[0.123, -0.456, ...]'::vector);

-- 検索例（クエリベクトルはアプリで OpenAI により生成）
-- SELECT content,
--        embedding <=> '[...]'::vector AS distance
-- FROM public.qualitative_data
-- ORDER BY distance
-- LIMIT 10;
