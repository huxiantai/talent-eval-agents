DO $$ BEGIN
    CREATE TYPE chunking_status AS ENUM ('pending', 'running', 'succeeded', 'failed');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE chunk_strategy AS ENUM ('fixed', 'recursive', 'markdown', 'semantic', 'interview_qa');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS chunking_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parse_job_id UUID NOT NULL REFERENCES parse_jobs(id),
    strategy chunk_strategy NOT NULL,
    status chunking_status NOT NULL DEFAULT 'pending',
    chunk_size INTEGER NOT NULL CHECK (chunk_size > 0),
    chunk_overlap INTEGER NOT NULL DEFAULT 0 CHECK (chunk_overlap >= 0),
    chunker_version VARCHAR(64) NOT NULL DEFAULT 'lesson-5-v1',
    embedding_model VARCHAR(128),
    configuration JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_chunking_runs_parse_job ON chunking_runs (parse_job_id, created_at DESC);

CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunking_run_id UUID NOT NULL REFERENCES chunking_runs(id) ON DELETE CASCADE,
    document_version_id UUID NOT NULL REFERENCES document_versions(id),
    candidate_id VARCHAR(64) NOT NULL,
    document_type VARCHAR(64) NOT NULL,
    permission_scope VARCHAR(64) NOT NULL,
    stable_key VARCHAR(64) NOT NULL,
    position INTEGER NOT NULL CHECK (position >= 0),
    chunk_level VARCHAR(16) NOT NULL DEFAULT 'child' CHECK (chunk_level IN ('parent', 'child')),
    content TEXT NOT NULL,
    element_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    heading_path JSONB NOT NULL DEFAULT '[]'::jsonb,
    parent_chunk_id UUID REFERENCES document_chunks(id),
    previous_chunk_id UUID REFERENCES document_chunks(id),
    next_chunk_id UUID REFERENCES document_chunks(id),
    page_start INTEGER,
    page_end INTEGER,
    timestamp_start DOUBLE PRECISION,
    timestamp_end DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (chunking_run_id, stable_key)
);

CREATE INDEX IF NOT EXISTS idx_document_chunks_version ON document_chunks (document_version_id, position);
CREATE INDEX IF NOT EXISTS idx_document_chunks_candidate ON document_chunks (candidate_id, document_type);

CREATE TABLE IF NOT EXISTS chunk_boundary_annotations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_version_id UUID NOT NULL REFERENCES document_versions(id),
    after_element_id VARCHAR(128) NOT NULL,
    after_position INTEGER NOT NULL CHECK (after_position > 0),
    reason VARCHAR(255),
    annotator VARCHAR(128) NOT NULL DEFAULT 'course-annotator',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_version_id, after_element_id, annotator)
);

CREATE TABLE IF NOT EXISTS chunk_evidence_questions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_version_id UUID NOT NULL REFERENCES document_versions(id),
    question TEXT NOT NULL,
    required_element_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    annotator VARCHAR(128) NOT NULL DEFAULT 'course-annotator',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
