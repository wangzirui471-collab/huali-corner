import unittest
import test_trial_http as fixtures


class NotificationHttpTests(unittest.TestCase):
    setUp = fixtures.TrialHttpTests.setUp
    tearDown = fixtures.TrialHttpTests.tearDown
    req = fixtures.TrialHttpTests.req
    register = fixtures.TrialHttpTests.register

    def test_notification_api_requires_login_and_does_not_accept_recipient_override(self):
        self.assertEqual(self.req('/api/notifications')[0], 401)
        session = self.register()
        token, user_id = session['token'], session['user']['id']
        with self.server.market.tx() as connection:
            self.server.market.notify(connection, [user_id], 'http-test', '订单有更新', 'order', 1)
        status, alerts = self.req('/api/notifications', token=token)
        self.assertEqual(status, 200)
        self.assertEqual(alerts['unread_count'], 1)
        self.assertEqual(self.req('/api/notifications/read', {'id': alerts['items'][0]['id'], 'user_id': 999}, token)[0], 400)
        self.assertEqual(self.req('/api/notifications/read', {'id': alerts['items'][0]['id']}, token)[0], 200)
        self.assertEqual(self.req('/api/notifications', token=token)[1]['unread_count'], 0)

    def test_location_choices_include_undergraduate_screenshot_and_custom_entry(self):
        status, config = self.req('/api/config')
        self.assertEqual(status, 200)
        self.assertIn('C1', config['buildings'])
        self.assertIn('B9', config['buildings'])
        self.assertIn('C5', config['building_groups'][0]['buildings'])
        self.assertTrue(config['custom_location_allowed'])
