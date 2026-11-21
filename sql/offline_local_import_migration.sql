-- RUN ONLY against isolated PostgreSQL database offline_staging_api.
CREATE TABLE IF NOT EXISTS offline_local_imports (
  local_uuid UUID PRIMARY KEY,
  tournament_id INTEGER NOT NULL UNIQUE REFERENCES tournaments(id) ON DELETE CASCADE,
  organizer_id INTEGER NOT NULL REFERENCES organizers(id),
  payload_sha256 CHAR(64) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
