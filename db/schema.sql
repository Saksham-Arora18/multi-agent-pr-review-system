

CREATE EXTENSION IF NOT EXISTS vector;

-- One row per PR we've seen. This is the "case file".
CREATE TABLE IF NOT EXISTS pull_requests (
    id SERIAL PRIMARY KEY,
    repo TEXT NOT NULL,
    pr_number INT NOT NULL,
    title TEXT,
    author TEXT,
    status TEXT DEFAULT 'open',       -- open, merged, closed
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (repo, pr_number)
);

-- One row per review cycle on a PR (a PR can be reviewed multiple times
-- as commits get pushed). Keeps history instead of overwriting.
CREATE TABLE IF NOT EXISTS review_runs (
    id SERIAL PRIMARY KEY,
    pr_id INT REFERENCES pull_requests(id) ON DELETE CASCADE,
    commit_sha TEXT,
    triggered_at TIMESTAMPTZ DEFAULT now(),
    status TEXT DEFAULT 'running'     -- running, awaiting_human, completed, failed
);

-- Chunked diff + related file content, embedded for retrieval.
-- This is what the retrieval agent searches over.
CREATE TABLE IF NOT EXISTS pr_chunks (
    id SERIAL PRIMARY KEY,
    pr_id INT REFERENCES pull_requests(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    chunk_type TEXT NOT NULL,         -- 'diff', 'full_file', 'past_pr_comment'
    content TEXT NOT NULL,
    embedding vector(384),            -- matches BAAI/bge-small-en-v1.5 dimension
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Vector similarity index for fast retrieval.
CREATE INDEX IF NOT EXISTS pr_chunks_embedding_idx
    ON pr_chunks USING hnsw (embedding vector_cosine_ops);

-- Every comment any agent produces, before it's posted.
-- This is where confidence scoring + failure-mode tagging lives.
CREATE TABLE IF NOT EXISTS review_comments (
    id SERIAL PRIMARY KEY,
    review_run_id INT REFERENCES review_runs(id) ON DELETE CASCADE,
    agent_name TEXT NOT NULL,         -- logic, security, style, tests
    file_path TEXT,
    line_number INT,
    comment TEXT NOT NULL,
    confidence_score FLOAT,           -- 0.0 - 1.0
    failure_type TEXT,                -- 'engineering', 'llm_uncertain', null if not flagged
    status TEXT DEFAULT 'pending',    -- pending, auto_posted, held_for_human, rejected, approved
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS review_comments_run_idx ON review_comments(review_run_id);
CREATE INDEX IF NOT EXISTS pr_chunks_pr_idx ON pr_chunks(pr_id);