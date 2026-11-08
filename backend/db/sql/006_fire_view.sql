-- One definition of "a fire", and the one date window the project works in.

CREATE OR REPLACE VIEW v_fire AS
SELECT *
FROM fire_events
WHERE cell_id IS NOT NULL
  AND confidence IN ('n', 'h')
  AND COALESCE(detection_type, 0) = 0;

-- Single row. Everything that builds the map, the dataset or the model reads its dates from here.
CREATE TABLE IF NOT EXISTS data_window (
    only_row   boolean PRIMARY KEY DEFAULT true CHECK (only_row),
    start_date date NOT NULL,
    end_date   date NOT NULL,
    CHECK (start_date <= end_date)
);

INSERT INTO data_window (start_date, end_date) VALUES ('2018-04-01', '2024-03-18')
ON CONFLICT (only_row) DO UPDATE SET start_date = EXCLUDED.start_date, end_date = EXCLUDED.end_date;
