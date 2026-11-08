-- The period for which BOTH fire labels and features (weather + NDVI) are loaded for the pilot.
-- The training export reads this. Widen feature_end after loading 2021+ weather.
ALTER TABLE data_window ADD COLUMN IF NOT EXISTS feature_start date;
ALTER TABLE data_window ADD COLUMN IF NOT EXISTS feature_end   date;
UPDATE data_window SET feature_start = COALESCE(feature_start, '2018-04-01'), feature_end = COALESCE(feature_end, '2020-12-31');
