-- 办公工单的人工确认快照和幂等回执。此文件仅为可审阅的迁移，尚未对真实数据库执行。
-- 先核对数据库权威源并导出备份；应用发布与真实数据库迁移需单独安排。
CREATE TABLE IF NOT EXISTS ai_office_jobs(
    id TEXT PRIMARY KEY,
    actor INTEGER NOT NULL,
    payload TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending',
    created REAL NOT NULL,
    expires REAL NOT NULL,
    result TEXT
);
