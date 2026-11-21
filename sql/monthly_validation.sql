-- Recalculate monthly outcomes from raw fields, independently of Python summaries.
-- The flights table contains the combined LAX records; no missing delay is filled.
SELECT
    CAST(Month AS INTEGER) AS month,
    COUNT(*) AS scheduled_flights,
    SUM(CASE WHEN Cancelled = 1 THEN 1 ELSE 0 END) AS cancelled_flights,
    SUM(CASE WHEN Diverted = 1 THEN 1 ELSE 0 END) AS diverted_flights,
    SUM(CASE WHEN Cancelled = 0 AND Diverted = 0 THEN 1 ELSE 0 END)
        AS completed_nondiverted_flights,
    SUM(CASE WHEN Cancelled = 0 AND Diverted = 0 AND ArrDelay IS NOT NULL
             THEN 1 ELSE 0 END) AS arrival_delay_eligible_flights,
    SUM(CASE WHEN Cancelled = 0 AND Diverted = 0 AND ArrDelay >= 15
             THEN 1 ELSE 0 END) AS arrivals_delayed_15_plus,
    SUM(CASE WHEN ArrDelay IS NULL THEN 1 ELSE 0 END) AS missing_arrival_delay
FROM flights
WHERE Origin = 'LAX'
  AND FlightDate >= '2025-01-01'
  AND FlightDate <= '2025-12-31'
GROUP BY CAST(Month AS INTEGER)
ORDER BY month;
