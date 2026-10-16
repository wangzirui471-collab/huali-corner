"""Release only a reserved item; account restrictions survive order cancellation."""
def release_product(connection,product_id):
    row=connection.execute('SELECT u.trading_blocked,u.is_active FROM products p JOIN users u ON u.id=p.seller_id WHERE p.id=?',(product_id,)).fetchone()
    blocked=not row or row['trading_blocked'] or not row['is_active']
    connection.execute("UPDATE products SET status=?,removal_reason=? WHERE id=? AND status='reserved'",
                       ('removed' if blocked else 'available','credit_block' if blocked else '',product_id))
