-- Enable PostGIS on first database initialization.
-- Runs automatically via the postgres image's docker-entrypoint-initdb.d hook.
CREATE EXTENSION IF NOT EXISTS postgis;
