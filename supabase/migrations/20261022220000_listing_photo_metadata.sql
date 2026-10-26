ALTER TABLE app.listing_photos
    ADD COLUMN width integer NOT NULL CHECK (width > 0),
    ADD COLUMN height integer NOT NULL CHECK (height > 0),
    ADD COLUMN thumb_path text NOT NULL;

ALTER TABLE app.listing_photos
    DROP CONSTRAINT listing_photos_listing_position_key,
    ADD CONSTRAINT listing_photos_listing_position_key
        UNIQUE (listing_id, position) DEFERRABLE INITIALLY DEFERRED;
