-- pgvector コサイン距離検索の例（アプリは Python でクエリを埋め込み、:vec 相当を渡す）

-- SELECT content,
--        embedding <=> $1::vector AS distance
-- FROM public.transcript_vector_chunks
-- ORDER BY distance
-- LIMIT 10;
