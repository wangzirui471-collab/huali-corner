"""Additive catalog migration, shared by old main and feature databases."""
def migrate_catalog(c):
    additions={'products':[('version','INTEGER NOT NULL DEFAULT 1'),('removal_reason',"TEXT NOT NULL DEFAULT ''")],
               'offers':[('product_version','INTEGER NOT NULL DEFAULT 1')]}
    for table,columns in additions.items():
        existing={row[1] for row in c.execute('PRAGMA table_info('+table+')')}
        for name,definition in columns:
            if name not in existing:c.execute('ALTER TABLE '+table+' ADD COLUMN '+name+' '+definition)
    c.execute("UPDATE products SET removal_reason=CASE WHEN EXISTS(SELECT 1 FROM users u WHERE u.id=products.seller_id AND u.trading_blocked=1) THEN 'credit_block' WHEN EXISTS(SELECT 1 FROM orders o,json_each(o.items) i WHERE o.status='refunded' AND json_extract(i.value,'$.id')=products.id) THEN 'refund_removed' ELSE 'legacy_unknown' END WHERE status='removed' AND removal_reason=''")
    c.execute('CREATE INDEX IF NOT EXISTS products_search_status_category ON products(status,category,id)')
