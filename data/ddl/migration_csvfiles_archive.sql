-- Migration script to add archive_id column to existing csvfiles table
ALTER TABLE csvfiles ADD COLUMN archive_id INTEGER DEFAULT NULL REFERENCES archive(id);
