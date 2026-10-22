ALTER TABLE app.notifications
    DROP CONSTRAINT notifications_kind_check;

ALTER TABLE app.notifications
    ADD CONSTRAINT notifications_kind_check
    CHECK (kind IN ('property_connected', 'profile_connected', 'saved_listing_changed'));
