import unittest

import test_trial_http as fixtures


class OperationsHttpTests(unittest.TestCase):
    setUp = fixtures.TrialHttpTests.setUp
    tearDown = fixtures.TrialHttpTests.tearDown
    req = fixtures.TrialHttpTests.req
    register = fixtures.TrialHttpTests.register

    def test_support_routes_require_admin_and_disable_sessions(self):
        self.server.market.bootstrap_admin('13900000080', 'OperatorPassword2026!')
        administrator = self.server.market.login_password('13900000080', 'OperatorPassword2026!')['token']
        ordinary = self.register()['token']
        payload = {'phone': '13900000081', 'password': 'SupportPassword2026!', 'nickname': '客服乙'}
        self.assertEqual(self.req('/api/admin/support', payload, ordinary)[0], 403)
        status, support = self.req('/api/admin/support', payload, administrator)
        self.assertEqual(status, 200, support)
        self.assertEqual(support['role'], 'support')
        token = self.server.market.login_password(payload['phone'], payload['password'])['token']
        self.assertEqual(self.req('/api/admin/support', token=token)[0], 403)
        self.assertEqual(self.req('/api/admin/support/active', {'user_id': support['id'], 'is_active': 'false'}, administrator)[0], 400)
        self.assertEqual(self.req('/api/admin/support/active', {'user_id': support['id'], 'is_active': False}, administrator)[0], 200)
        self.assertEqual(self.req('/api/me', token=token)[0], 401)

    def test_published_credit_rules_are_readable_without_granting_privileges(self):
        ordinary = self.register()['token']
        status, rules = self.req('/api/credit/rules', token=ordinary)
        self.assertEqual(status, 200, rules)
        self.assertTrue(any(rule['key'] == 'hidden_defect' and rule['delta'] == -15 for rule in rules))
        self.assertEqual(self.req('/api/seller/products', token=ordinary), (200, []))
        self.assertEqual(self.req('/api/credit/penalty', {
            'target_user_id': 1, 'ticket_id': 1, 'rule_key': 'fraud', 'reason': '普通用户不能处罚',
        }, ordinary)[0], 403)
