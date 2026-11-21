-- Independent point estimates at a bound :threshold, with the original support rule.
WITH selected AS (
    SELECT DOT_ID_Reporting_Airline, DestAirportID, Month,
           CASE WHEN CAST(CRSDepTime AS INTEGER) >= 600 AND CAST(CRSDepTime AS INTEGER) < 1000 THEN 'morning'
                WHEN CAST(CRSDepTime AS INTEGER) >= 1700 AND CAST(CRSDepTime AS INTEGER) < 2100 THEN 'evening'
                ELSE NULL END AS window,
           CASE WHEN Cancelled = 1 OR Diverted = 1 OR ArrDelay >= :threshold THEN 1 ELSE 0 END AS event
    FROM flights WHERE Origin = 'LAX' AND Year = 2025
), groups AS (
    SELECT DOT_ID_Reporting_Airline, DestAirportID, Month,
           SUM(CASE WHEN window = 'morning' THEN 1 ELSE 0 END) AS nm,
           SUM(CASE WHEN window = 'evening' THEN 1 ELSE 0 END) AS ne,
           SUM(CASE WHEN window = 'morning' THEN event ELSE 0 END) AS ym,
           SUM(CASE WHEN window = 'evening' THEN event ELSE 0 END) AS ye
    FROM selected WHERE window IS NOT NULL
    GROUP BY DOT_ID_Reporting_Airline, DestAirportID, Month
), supported AS (
    SELECT *, nm + ne AS pooled FROM groups WHERE nm >= :minimum AND ne >= :minimum
)
SELECT DestAirportID, COUNT(*) AS groups, SUM(nm) AS morning_flights, SUM(ne) AS evening_flights,
       SUM(1.0 * pooled * ym / nm) / SUM(pooled) AS morning_rate,
       SUM(1.0 * pooled * ye / ne) / SUM(pooled) AS evening_rate
FROM supported GROUP BY DestAirportID ORDER BY DestAirportID;
