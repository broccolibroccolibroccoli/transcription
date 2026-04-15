-- Ollama nomic-embed-text（768 次元）用。OpenAI 1536 版と併用しない場合はこの定義でテーブルを1つにする。
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
    embedding VECTOR(768) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_transcript_vector_chunks_file_id
    ON public.transcript_vector_chunks (file_id);
