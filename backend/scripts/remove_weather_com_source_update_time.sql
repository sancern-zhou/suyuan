-- Run against the XcAiDb SQL Server database, not the PostgreSQL application DB.
-- Idempotent; refuse to discard a timestamp if a deployment has populated it.
SET XACT_ABORT ON;
BEGIN TRANSACTION;
IF COL_LENGTH(N'dbo.XuchangWeatherComDailyForecast', N'source_update_time') IS NOT NULL
BEGIN
    EXEC(N'IF EXISTS (SELECT 1 FROM dbo.XuchangWeatherComDailyForecast
                     WHERE source_update_time IS NOT NULL)
               THROW 50001, ''source_update_time contains values; migration stopped'', 1;');
    ALTER TABLE dbo.XuchangWeatherComDailyForecast DROP COLUMN source_update_time;
END;
COMMIT TRANSACTION;
