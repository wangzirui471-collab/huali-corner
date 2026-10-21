-- 新原子写入适配器使用的失败断言表；正常提交不会向此表写入记录。
-- 在隔离环境应用并验证后才可接入业务；此文件尚未应用于真实数据库。
CREATE TABLE refactor_atomic_assertions (
    assertion_key TEXT PRIMARY KEY,
    ok INTEGER NOT NULL CONSTRAINT huali_atomic_assertion CHECK (ok = 1)
);
