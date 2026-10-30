SET NOCOUNT ON;
CREATE TABLE #want (name_lower nvarchar(200) PRIMARY KEY);
INSERT INTO #want (name_lower) VALUES
('rf_ruleitemtask'),('sec_configdata'),('rf_hy_humidity'),('sec_flightcheck'),
('drt_beta'),('drt_gasanalyzer'),('drt_gasanalyzer_fiveparameters'),('drt_gasanalyzer_nox'),('drt_teom'),
('pw_unitplan'),('mtc_workingorderlog');

SELECT t.name AS table_name, c.name AS col_name, ty.name AS data_type, c.max_length,
       c.is_nullable, CASE WHEN pk.column_id IS NOT NULL THEN 1 ELSE 0 END AS is_pk, c.column_id
FROM sys.tables t
JOIN #want w ON w.name_lower = LOWER(t.name)
JOIN sys.columns c ON c.object_id = t.object_id
JOIN sys.types ty ON ty.user_type_id = c.user_type_id
LEFT JOIN (
    SELECT ic.object_id, ic.column_id FROM sys.indexes i
    JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
    WHERE i.is_primary_key = 1
) pk ON pk.object_id = t.object_id AND pk.column_id = c.column_id
ORDER BY t.name, c.column_id;

SELECT 'RF_ITEM_META' AS marker, c.name AS col_name, ty.name AS data_type
FROM sys.columns c JOIN sys.types ty ON ty.user_type_id = c.user_type_id
WHERE c.object_id = OBJECT_ID('dbo.RF_ITEM') ORDER BY c.column_id;
