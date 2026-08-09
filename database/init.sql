CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TYPE document_status AS ENUM ('active', 'inactive', 'deleted');
CREATE TYPE parse_status AS ENUM ('pending', 'running', 'succeeded', 'partially_succeeded', 'failed');

CREATE TABLE employee_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_no VARCHAR(64) NOT NULL UNIQUE,
    tenant_id VARCHAR(64) NOT NULL DEFAULT 'course-demo',
    name VARCHAR(128) NOT NULL,
    gender VARCHAR(16),
    birth_date DATE,
    region VARCHAR(128),
    current_position VARCHAR(255),
    job_level VARCHAR(64) CHECK (job_level IS NULL OR job_level ~ '^L[0-9]+$'),
    years_of_experience DOUBLE PRECISION CHECK (years_of_experience >= 0),
    department VARCHAR(255),
    employment_status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE knowledge_bases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(64) NOT NULL DEFAULT 'course-demo',
    name VARCHAR(255) NOT NULL,
    description TEXT,
    permission_scope VARCHAR(64) NOT NULL DEFAULT 'hr_private',
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, name)
);

CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id VARCHAR(64) NOT NULL,
    material_no VARCHAR(64) UNIQUE,
    employee_id UUID REFERENCES employee_profiles(id),
    knowledge_base_id UUID REFERENCES knowledge_bases(id),
    tenant_id VARCHAR(64) NOT NULL,
    title VARCHAR(255) NOT NULL,
    document_type VARCHAR(64) NOT NULL,
    source VARCHAR(64) NOT NULL DEFAULT 'manual_upload',
    permission_scope VARCHAR(64) NOT NULL DEFAULT 'hr_private',
    confidentiality_level VARCHAR(32) NOT NULL DEFAULT 'internal',
    status document_status NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_documents_employee ON documents (employee_id);
CREATE INDEX idx_documents_knowledge_base ON documents (knowledge_base_id);

CREATE TABLE file_objects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bucket_name VARCHAR(128) NOT NULL,
    object_key VARCHAR(1024) NOT NULL UNIQUE,
    original_name VARCHAR(512) NOT NULL,
    mime_type VARCHAR(255) NOT NULL,
    size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
    sha256 CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_file_objects_sha256 ON file_objects (sha256);

CREATE TABLE document_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id),
    file_object_id UUID NOT NULL REFERENCES file_objects(id),
    version_no INTEGER NOT NULL CHECK (version_no > 0),
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, version_no)
);

CREATE UNIQUE INDEX uq_document_current_version
ON document_versions (document_id) WHERE is_current;

CREATE TABLE parse_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_version_id UUID NOT NULL REFERENCES document_versions(id),
    parser_name VARCHAR(64) NOT NULL,
    parser_version VARCHAR(64),
    status parse_status NOT NULL DEFAULT 'pending',
    progress SMALLINT NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
    retry_count SMALLINT NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    error_code VARCHAR(64),
    error_message TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_parse_jobs_status_created ON parse_jobs (status, created_at);

CREATE TABLE parse_artifacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parse_job_id UUID NOT NULL REFERENCES parse_jobs(id) ON DELETE CASCADE,
    artifact_type VARCHAR(64) NOT NULL,
    bucket_name VARCHAR(128) NOT NULL,
    object_key VARCHAR(1024) NOT NULL,
    content_type VARCHAR(255) NOT NULL,
    size_bytes BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (parse_job_id, artifact_type, object_key)
);

CREATE TABLE document_metadata (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    metadata_key VARCHAR(128) NOT NULL,
    metadata_value JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, metadata_key)
);

COMMENT ON TABLE documents IS '业务层逻辑文档，同一文档可以有多个文件版本';
COMMENT ON TABLE employee_profiles IS '员工花名册结构化基础信息';
COMMENT ON TABLE knowledge_bases IS '档案资料库中的知识库';
COMMENT ON TABLE file_objects IS '对象存储中的物理文件索引';
COMMENT ON TABLE document_versions IS '逻辑文档与物理文件之间的版本关系';
COMMENT ON TABLE parse_jobs IS '文件解析任务及状态变化';
COMMENT ON TABLE parse_artifacts IS 'Markdown、JSON、图片、转写等解析产物索引';
