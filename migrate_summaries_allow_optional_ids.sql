-- Migration: Allow summaries to be created with either emr_id or encounter_id (or both),
-- but not neither. This relaxes the NOT NULL constraints on emr_id/encounter_id and adds
-- a CHECK constraint to enforce that at least one is present.

ALTER TABLE summaries
    ALTER COLUMN emr_id DROP NOT NULL,
    ALTER COLUMN encounter_id DROP NOT NULL;

ALTER TABLE summaries
    DROP CONSTRAINT IF EXISTS summaries_emr_or_encounter_not_null,
    ADD CONSTRAINT summaries_emr_or_encounter_not_null
        CHECK (emr_id IS NOT NULL OR encounter_id IS NOT NULL);

