-- PostgreSQL + pgvector（アプリ側でチャンク化・OpenAI 埋め込み・INSERT）
-- OpenAI text-embedding-3-small 等: VECTOR(1536)。Ollama 等768 次元なら vector_transcript_setup_ollama.sql を使う。

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS public.transcript_vector_chunks (
    id SERIAL PRIMARY KEY,
    file_id INTEGER NOT NULL,
    filename TEXT,
    project_id INTEGER,
    project_name TEXT,
    segment_index INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    speaker TEXT,
    start_time_sec DOUBLE PRECISION,
    end_time_sec DOUBLE PRECISION,
    content TEXT NOT NULL,
    embedding VECTOR(1536) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_transcript_vector_chunks_file_id
    ON public.transcript_vector_chunks (file_id);

-- データ件数が増えたら ANN 用インデックスを検討（要 ANALYZE）
-- CREATE INDEX idx_transcript_vector_chunks_embedding
--   ON public.transcript_vector_chunks
--   USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
