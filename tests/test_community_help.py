"""Structured community help is a bulletin, never a payment or service order."""
import time
import unittest
import test_publishing as fixtures
from app.market import DomainError, Market


class CommunityHelpTests(unittest.TestCase):
    setUp = fixtures.PublishingTests.setUp
    login = fixtures.PublishingTests.login

    def publish(self, **changes):
        data=dict(kind='need',service_type='parcel',title='帮取一件小快递',body='今晚有课，取件码私聊提供',
                  reward_yuan='3.50',place='C1楼下公共入口',deadline=time.time()+7200)
        data.update(changes)
        return self.market.publish_help(self.seller,data)

    def test_publish_filter_and_contact_without_funds_or_private_fields(self):
        post=self.publish()
        self.assertEqual(post['reward'],350)
        self.assertEqual(post['status'],'open')
        self.assertNotIn('phone',post)
        feed=self.market.help_posts(self.buyer,{'service_type':'parcel','kind':'need'})
        self.assertEqual(feed['items'][0]['id'],post['id'])
        self.assertEqual(self.market.help_posts(self.buyer,{'service_type':'moving'})['items'],[])
        room=self.market.private_room(self.buyer,post['user_id'])
        self.assertEqual(room['peer_id'],self.seller)
        self.assertEqual(self.market.rows('SELECT * FROM orders'),[])
        self.assertEqual(self.market.rows('SELECT * FROM ledger'),[])
        self.assertEqual(Market(self.tmp.name).help_posts()['items'][0]['id'],post['id'])

    def test_owner_can_close_but_other_user_cannot_and_expiry_is_visible(self):
        post=self.publish(deadline=time.time()+120)
        with self.assertRaises(DomainError):self.market.set_help_status(self.buyer,post['id'],'closed')
        self.market.set_help_status(self.seller,post['id'],'closed')
        self.assertEqual(self.market.help_posts()['items'],[])
        self.assertEqual(self.market.help_posts(self.seller,{'mine':'1','status':'all'})['items'][0]['status'],'closed')
        self.market.set_help_status(self.seller,post['id'],'open')
        with self.market.tx() as c:c.execute('UPDATE service_posts SET deadline=? WHERE post_id=?',(time.time()-1,post['id']))
        self.assertEqual(self.market.help_posts()['items'],[])
        self.assertEqual(self.market.help_posts(self.seller,{'mine':'1','status':'all'})['items'][0]['status'],'expired')
        with self.assertRaises(DomainError):self.market.set_help_status(self.seller,post['id'],'open')

    def test_validation_negotiable_free_and_bounded_paging(self):
        for change in [dict(service_type='invalid'),dict(kind='invalid'),dict(reward_yuan='-1'),dict(reward_yuan='0.001'),dict(deadline=0)]:
            with self.assertRaises(DomainError):self.publish(**change)
        self.assertEqual(self.publish(reward_yuan='0')['reward'],0)
        self.assertIsNone(self.publish(reward_yuan='')['reward'])
        first=self.market.help_posts(None,{'page_size':'1'})
        second=self.market.help_posts(None,{'page_size':'1','before_id':str(first['next_cursor'])})
        self.assertNotEqual(first['items'][0]['id'],second['items'][0]['id'])

    def test_report_is_linked_and_own_poster_cannot_review(self):
        post=self.publish()
        ticket=self.market.create_ticket(self.buyer,dict(type='report',post_id=post['id'],subject='互助反馈',body='提供核实材料'))
        self.assertEqual(ticket['post_id'],post['id'])
        with self.market.tx() as c:c.execute("UPDATE users SET role='support' WHERE id=?",(self.seller,))
        with self.assertRaises(DomainError):self.market.resolve_ticket(self.seller,ticket['id'],dict(outcome='resolved',reason='不能审自己'))
        self.market.resolve_ticket(self.admin,ticket['id'],dict(outcome='resolved',reason='核实材料'))
        self.market.apply_penalty(self.admin,self.seller,ticket['id'],'description_omission','核实发布信息遗漏')
        self.assertEqual(self.market.profile(self.seller)['score'],95)

    def test_restricted_accounts_cannot_create_or_reopen_but_can_close(self):
        post=self.publish()
        with self.market.tx() as c:c.execute('UPDATE users SET score=59 WHERE id=?',(self.seller,))
        with self.assertRaises(DomainError):self.publish()
        self.market.set_help_status(self.seller,post['id'],'closed')
        with self.assertRaises(DomainError):self.market.set_help_status(self.seller,post['id'],'open')

    def test_structured_help_never_leaks_as_unlabelled_generic_recruitment(self):
        post=self.publish()
        self.market.set_help_status(self.seller,post['id'],'closed')
        self.assertNotIn(post['id'],[row['id'] for row in self.market.posts()])


if __name__=='__main__':unittest.main()
