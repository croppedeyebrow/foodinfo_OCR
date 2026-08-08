-- Destructive rollback. Run only after backing up metadata and stopping writers.
DROP SCHEMA IF EXISTS pipeline_metadata CASCADE;
