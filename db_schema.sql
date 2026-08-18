-- SQL Schema Initialization Script for Supabase PostgreSQL
-- Copy and run this script directly inside the Supabase SQL Editor.

-- 1. Create clusters table
CREATE TABLE IF NOT EXISTS clusters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) UNIQUE NOT NULL,
    environment VARCHAR(100) NOT NULL,
    api_server VARCHAR(512) NOT NULL,
    status VARCHAR(50) DEFAULT 'active' NOT NULL,
    last_seen_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- 2. Create assets table
CREATE TABLE IF NOT EXISTS assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cluster_id UUID NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    workload_uid VARCHAR(255) NOT NULL,
    asset_name VARCHAR(255) NOT NULL,
    asset_type VARCHAR(50) NOT NULL,
    namespace VARCHAR(255) NOT NULL,
    workload_kind VARCHAR(100) NOT NULL,
    workload_name VARCHAR(255) NOT NULL,
    image_references JSONB NOT NULL DEFAULT '[]'::jsonb,
    owner VARCHAR(255) DEFAULT 'unassigned' NOT NULL,
    owner_source VARCHAR(100) DEFAULT 'unassigned' NOT NULL,
    risk_tier VARCHAR(50) DEFAULT 'low' NOT NULL,
    risk_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    detection_confidence FLOAT DEFAULT 0.0 NOT NULL,
    detection_evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    first_seen_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    last_active_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    status VARCHAR(50) DEFAULT 'active' NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT uq_cluster_workload UNIQUE (cluster_id, workload_uid)
);

-- 3. Create discovery_events table
CREATE TABLE IF NOT EXISTS discovery_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    before_snapshot JSONB,
    after_snapshot JSONB,
    observed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- 4. Create alerts table
CREATE TABLE IF NOT EXISTS alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    severity VARCHAR(50) DEFAULT 'medium' NOT NULL,
    type VARCHAR(100) NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    status VARCHAR(50) DEFAULT 'open' NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    resolved_at TIMESTAMP WITH TIME ZONE
);
