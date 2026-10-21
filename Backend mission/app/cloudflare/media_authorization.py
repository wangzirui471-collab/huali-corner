"""Read authorization over existing media references, without a schema cutover.

Keep JSON compatibility at this adapter boundary. The structured media relations
planned for T03 can replace these queries without changing the HTTP contract.
"""

from .d1 import Database


async def can_read_upload(
    db: Database, upload_id: str, actor_id: int | None, ticket_id: int | None
) -> bool:
    """Roles alone never grant access to order history or private proof."""
    row = await db.first(
        """
        WITH resource AS (
            SELECT * FROM uploads WHERE id=?1
        ), actor AS (
            SELECT id,role FROM users WHERE id=?2 AND status='active'
        ), resource_products AS (
            SELECT p.id,p.status,p.seller_id
            FROM products p,resource r
            WHERE p.seller_id=r.user_id AND (
                (r.private=1 AND json_extract(p.data,'$.proof')=r.id)
                OR (r.private=0 AND EXISTS (
                    SELECT 1 FROM json_each(p.data,'$.photos') photo
                    WHERE json_extract(photo.value,'$.id')=r.id
                       OR json_extract(photo.value,'$.url')='/media/'||r.id
                ))
            )
        ), resource_orders AS (
            SELECT o.id,o.buyer_id,o.seller_id
            FROM orders o,resource r
            WHERE o.seller_id=r.user_id AND EXISTS (
                SELECT 1 FROM json_each(o.items) item
                WHERE json_extract(item.value,'$.id') IN (
                    SELECT id FROM resource_products
                ) OR (r.private=0
                      AND json_extract(item.value,'$.photo')='/media/'||r.id)
            )
        )
        SELECT 1 FROM resource r WHERE
            EXISTS (SELECT 1 FROM actor WHERE id=r.user_id)
            OR (r.private=0 AND (
                EXISTS (
                    SELECT 1 FROM resource_products p JOIN users u ON u.id=p.seller_id
                    WHERE p.status='available' AND u.status='active'
                ) OR EXISTS (
                    SELECT 1 FROM resource_orders o,actor a
                    WHERE a.id=o.buyer_id OR a.id=o.seller_id
                )
            ))
            OR EXISTS (
                SELECT 1 FROM tickets t,actor a
                WHERE t.id=?3 AND a.role IN ('support','admin','developer')
                  AND (t.product_id IN (SELECT id FROM resource_products)
                       OR t.order_id IN (SELECT id FROM resource_orders))
                  AND (t.assignee=a.id OR EXISTS (
                      SELECT 1 FROM rooms room
                      JOIN members member ON member.room_id=room.id
                      WHERE room.support=1 AND room.ticket_id=t.id
                        AND room.assignee=a.id AND member.user_id=a.id
                        AND room.support_status='open'
                  ))
                  AND t.user_id<>a.id
                  AND NOT EXISTS (
                      SELECT 1 FROM products p
                      WHERE p.id=t.product_id AND p.seller_id=a.id
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM orders o
                      WHERE (o.buyer_id=a.id OR o.seller_id=a.id)
                        AND (o.id=t.order_id OR EXISTS (
                            SELECT 1 FROM json_each(o.items) item
                            WHERE json_extract(item.value,'$.id')=t.product_id
                        ))
                  )
            )
        LIMIT 1
        """,
        (upload_id, actor_id, ticket_id),
    )
    return row is not None
