CREATE SCHEMA IF NOT EXISTS etl;

CREATE TABLE IF NOT EXISTS etl.transformation_runs (
    run_id UUID PRIMARY KEY,
    batch_id UUID NOT NULL,
    parent_extraction_run_id TEXT NOT NULL,
    batch_start DATE NOT NULL,
    batch_end_exclusive DATE NOT NULL,
    started_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at_utc TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (
        status IN ('APPROVED', 'MANUAL_REVIEW', 'REJECTED', 'FAILED')
    ),
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    rules_applied JSONB NOT NULL DEFAULT '{}'::jsonb,
    validations JSONB NOT NULL DEFAULT '[]'::jsonb,
    CHECK (batch_start < batch_end_exclusive),
    CHECK (ended_at_utc IS NULL OR ended_at_utc >= started_at_utc)
);

CREATE INDEX IF NOT EXISTS transformation_runs_batch_idx
    ON etl.transformation_runs (batch_id, started_at_utc DESC);

CREATE INDEX IF NOT EXISTS transformation_runs_retention_idx
    ON etl.transformation_runs (ended_at_utc)
    WHERE ended_at_utc IS NOT NULL;

CREATE TABLE IF NOT EXISTS etl.dim_child (
    batch_id UUID NOT NULL,
    run_id UUID NOT NULL REFERENCES etl.transformation_runs (run_id),
    child_key UUID NOT NULL,
    source_child_id UUID NOT NULL,
    date_of_birth DATE NOT NULL,
    barangay_name TEXT NOT NULL,
    purok_name TEXT NOT NULL,
    gender TEXT NOT NULL CHECK (gender IN ('MALE', 'FEMALE', 'UNKNOWN')),
    is_ip BOOLEAN NOT NULL,
    source_status TEXT NOT NULL CHECK (source_status = 'ACTIVE'),
    PRIMARY KEY (batch_id, child_key),
    UNIQUE (batch_id, source_child_id)
);

CREATE TABLE IF NOT EXISTS etl.fact_assessment (
    batch_id UUID NOT NULL,
    run_id UUID NOT NULL REFERENCES etl.transformation_runs (run_id),
    assessment_id UUID NOT NULL,
    child_key UUID NOT NULL,
    date_measured DATE NOT NULL,
    assessment_month CHAR(7) NOT NULL,
    age_months INTEGER NOT NULL CHECK (age_months >= 0),
    weight_kg DECIMAL(5,2) NOT NULL CHECK (weight_kg > 0),
    height_cm DECIMAL(5,2) NOT NULL CHECK (height_cm > 0),
    wfa_status TEXT NOT NULL,
    hfa_status TEXT NOT NULL,
    wfl_h_status TEXT NOT NULL,
    PRIMARY KEY (batch_id, assessment_id),
    FOREIGN KEY (batch_id, child_key)
        REFERENCES etl.dim_child (batch_id, child_key)
);

CREATE INDEX IF NOT EXISTS fact_assessment_trend_idx
    ON etl.fact_assessment (batch_id, assessment_month, child_key);

CREATE TABLE IF NOT EXISTS etl.fact_supplement (
    batch_id UUID NOT NULL,
    run_id UUID NOT NULL REFERENCES etl.transformation_runs (run_id),
    supplement_id UUID NOT NULL,
    child_key UUID NOT NULL,
    date_administered DATE NOT NULL,
    supplement_month CHAR(7) NOT NULL,
    supplement_type TEXT NOT NULL
        CHECK (supplement_type IN ('Vitamin A', 'Deworming')),
    dose_order INTEGER NOT NULL CHECK (dose_order > 0),
    age_months INTEGER NOT NULL CHECK (age_months >= 0),
    PRIMARY KEY (batch_id, supplement_id),
    FOREIGN KEY (batch_id, child_key)
        REFERENCES etl.dim_child (batch_id, child_key)
);

CREATE TABLE IF NOT EXISTS etl.fact_health_trends (
    batch_id UUID NOT NULL,
    run_id UUID NOT NULL REFERENCES etl.transformation_runs (run_id),
    barangay_name TEXT NOT NULL,
    assessment_month CHAR(7) NOT NULL,
    indicator TEXT NOT NULL CHECK (indicator IN ('WFA', 'HFA', 'WFL')),
    nutritional_status TEXT NOT NULL,
    total_count BIGINT NOT NULL CHECK (total_count > 0),
    PRIMARY KEY (
        batch_id,
        barangay_name,
        assessment_month,
        indicator,
        nutritional_status
    )
);

CREATE TABLE IF NOT EXISTS etl.transformation_profiles (
    profile_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES etl.transformation_runs (run_id),
    batch_id UUID NOT NULL,
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    issue_type TEXT NOT NULL,
    sample_values JSONB NOT NULL DEFAULT '[]'::jsonb,
    affected_records BIGINT NOT NULL CHECK (affected_records >= 0),
    input_records BIGINT NOT NULL CHECK (input_records >= 0),
    affected_percentage NUMERIC(6,2) NOT NULL
        CHECK (affected_percentage BETWEEN 0 AND 100),
    planned_treatment TEXT NOT NULL,
    rule_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS transformation_profiles_retention_idx
    ON etl.transformation_profiles (run_id);

CREATE TABLE IF NOT EXISTS etl.transformation_quarantine (
    quarantine_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES etl.transformation_runs (run_id),
    batch_id UUID NOT NULL,
    parent_extraction_run_id TEXT NOT NULL,
    table_name TEXT NOT NULL,
    source_record_id TEXT,
    rule_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    source_record JSONB NOT NULL,
    rejected_at_utc TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS transformation_quarantine_batch_idx
    ON etl.transformation_quarantine (batch_id, table_name);

CREATE INDEX IF NOT EXISTS transformation_quarantine_retention_idx
    ON etl.transformation_quarantine (rejected_at_utc);
