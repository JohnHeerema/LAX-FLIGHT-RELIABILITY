-- Recompute windows, the composite outcome, matching, and common-mix rates.
-- Bind :minimum from the already committed comparison protocol.
WITH selected AS (
    SELECT DOT_ID_Reporting_Airline, DestAirportID, Month,
           CASE WHEN CAST(CRSDepTime AS INTEGER) >= 600
                      AND CAST(CRSDepTime AS INTEGER) < 1000 THEN 'morning'
                WHEN CAST(CRSDepTime AS INTEGER) >= 1700
                      AND CAST(CRSDepTime AS INTEGER) < 2100 THEN 'evening'
                ELSE NULL END AS window,
           CASE WHEN Cancelled = 1 OR Diverted = 1 OR ArrDelay >= 15
                THEN 1 ELSE 0 END AS disrupted
    FROM flights
    WHERE Origin = 'LAX' AND Year = 2025
), pairs AS (
    SELECT DOT_ID_Reporting_Airline, DestAirportID, Month,
           SUM(CASE WHEN window = 'morning' THEN 1 ELSE 0 END) AS n_morning,
           SUM(CASE WHEN window = 'evening' THEN 1 ELSE 0 END) AS n_evening,
           SUM(CASE WHEN window = 'morning' THEN disrupted ELSE 0 END) AS y_morning,
           SUM(CASE WHEN window = 'evening' THEN disrupted ELSE 0 END) AS y_evening
    FROM selected
    WHERE window IS NOT NULL
    GROUP BY DOT_ID_Reporting_Airline, DestAirportID, Month
), supported AS (
    SELECT *, n_morning + n_evening AS pooled
    FROM pairs
    WHERE n_morning >= :minimum AND n_evening >= :minimum
)
SELECT COUNT(*) AS eligible_pairs,
       SUM(n_morning) AS n_morning,
       SUM(n_evening) AS n_evening,
       SUM(y_morning) AS disrupted_morning,
       SUM(y_evening) AS disrupted_evening,
       SUM(1.0 * pooled * y_morning / n_morning) / SUM(pooled) AS morning_rate,
       SUM(1.0 * pooled * y_evening / n_evening) / SUM(pooled) AS evening_rate
FROM supported;
