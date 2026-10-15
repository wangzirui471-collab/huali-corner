import hashlib
import json
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from market import Market, DomainError


class TrialAuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.market=Market(self.tmp.name,trial=True)
        self.password='StudyAtHuali-2026!'

    def register(self,phone='13900000011',nickname='试用同学'):
        return self.market.register_password(phone,self.password,nickname)

    def test_trial_starts_without_shared_accounts_and_disables_otp(self):
        self.assertEqual(self.market.rows('SELECT * FROM users'),[])
        with self.assertRaises(DomainError):self.market.request_code('13800000003')
        with self.assertRaises(DomainError):self.market.login('13800000003','123456')

    def test_registration_hashes_password_and_session_and_never_returns_phone(self):
        result=self.register()
        self.assertEqual(result['user']['role'],'user')
        self.assertEqual(result['user']['college'],'计算机工程学院')
        self.assertNotIn('phone',result['user'])
        self.assertFalse(result['phone_verified'])
        credential=self.market.row('SELECT * FROM password_credentials')
        self.assertNotIn(self.password,json.dumps(credential))
        self.assertNotIn(result['recovery_code'],json.dumps(credential))
        self.assertNotEqual(self.market.row('SELECT token FROM sessions')['token'],result['token'])
        login=self.market.login_password('13900000011',self.password)
        self.assertEqual(self.market.user(login['token']),result['user']['id'])
        self.assertNotIn('recovery_code',login)

    def test_duplicate_phone_or_demo_phone_cannot_claim_privileges(self):
        self.register()
        with self.assertRaises(DomainError):self.register()
        result=self.register('13800000003')
        self.assertEqual(result['user']['role'],'user')
        with self.assertRaises(DomainError):self.market.staff(result['user']['id'])

    def test_invalid_phone_or_short_or_oversized_password_rejected(self):
        for phone,password in [('bad',self.password),('13900000011','short'),('13900000011','x'*129)]:
            with self.subTest(phone=phone,length=len(password)),self.assertRaises(DomainError):
                self.market.register_password(phone,password,'同学')

    def test_unknown_phone_and_wrong_password_return_same_error(self):
        self.register()
        errors=[]
        for phone in ['13900000011','13900000099']:
            with self.assertRaises(DomainError) as context:self.market.login_password(phone,'WrongPassword2026!')
            errors.append((context.exception.status,str(context.exception)))
        self.assertEqual(errors[0],errors[1])

    def test_account_lockout_persists_across_restarts_and_expires(self):
        self.register()
        for _ in range(5):
            with self.assertRaises(DomainError):self.market.login_password('13900000011','WrongPassword2026!')
        restarted=Market(self.tmp.name,trial=True)
        with self.assertRaises(DomainError) as context:restarted.login_password('13900000011',self.password)
        self.assertEqual(context.exception.status,429)
        with patch('auth.time.time',return_value=time.time()+901):
            self.assertEqual(restarted.login_password('13900000011',self.password)['user']['role'],'user')

    def test_password_change_requires_old_password_and_revokes_all_sessions(self):
        result=self.register();uid=result['user']['id']
        other=self.market.login_password('13900000011',self.password)
        with self.assertRaises(DomainError):self.market.change_password(uid,'wrong','NewPassword-2026!')
        self.market.change_password(uid,self.password,'NewPassword-2026!')
        for token in [result['token'],other['token']]:
            with self.assertRaises(DomainError):self.market.user(token)
        with self.assertRaises(DomainError):self.market.login_password('13900000011',self.password)
        self.assertEqual(self.market.login_password('13900000011','NewPassword-2026!')['user']['id'],uid)

    def test_password_change_clears_previous_failed_login_lock(self):
        result=self.register()
        for _ in range(5):
            with self.assertRaises(DomainError):self.market.login_password('13900000011','WrongPassword2026!')
        self.market.change_password(result['user']['id'],self.password,'NewPassword-2026!')
        self.assertEqual(self.market.login_password('13900000011','NewPassword-2026!')['user']['id'],result['user']['id'])

    def test_recovery_requires_secret_rotates_code_and_revokes_sessions(self):
        result=self.register()
        with self.assertRaises(DomainError):self.market.recover_password('13900000011','wrong','NewPassword-2026!')
        reset=self.market.recover_password('13900000011',result['recovery_code'],'NewPassword-2026!')
        self.assertNotEqual(reset['recovery_code'],result['recovery_code'])
        with self.assertRaises(DomainError):self.market.user(result['token'])
        with self.assertRaises(DomainError):self.market.recover_password('13900000011',result['recovery_code'],'AnotherPassword-2026!')
        self.market.login_password('13900000011','NewPassword-2026!')

    def test_only_operator_can_provision_admin_and_restart_does_not_reset_password(self):
        result=self.market.bootstrap_admin('13900000088',self.password)
        self.assertEqual(result['role'],'admin')
        self.assertEqual(Market(self.tmp.name,trial=True).bootstrap_admin('13900000088','DifferentPassword-2026!')['id'],result['id'])
        self.market.login_password('13900000088',self.password)
        student=self.register()
        with self.assertRaises(DomainError):self.market.bootstrap_admin('13900000011',self.password)
        self.assertEqual(self.market.profile(student['user']['id'])['role'],'user')

    def test_demo_database_and_trial_database_cannot_be_mixed(self):
        with tempfile.TemporaryDirectory() as root:
            Market(root)
            with self.assertRaises(DomainError):Market(root,trial=True)
        with self.assertRaises(DomainError):Market(self.tmp.name)

    def test_two_accounts_persist_with_separate_private_resources(self):
        a=self.register();b=self.register('13900000022','另一位同学')
        ticket=self.market.create_ticket(a['user']['id'],{'type':'other','subject':'测试工单','body':'仅对本人可见'})
        with self.assertRaises(DomainError):self.market.ticket(b['user']['id'],ticket['id'])
        restarted=Market(self.tmp.name,trial=True)
        self.assertEqual(restarted.user(a['token']),a['user']['id'])
        self.assertEqual(restarted.user(b['token']),b['user']['id'])
        with self.assertRaises(DomainError):restarted.staff(b['user']['id'])

    def test_automatic_backup_restores_password_accounts_and_sessions(self):
        account=self.register()
        backup=self.market._backup()
        with tempfile.TemporaryDirectory() as restored_root:
            with zipfile.ZipFile(backup) as archive:archive.extractall(restored_root)
            restored=Market(restored_root,trial=True)
            self.assertEqual(restored.user(account['token']),account['user']['id'])
            self.assertEqual(restored.login_password('13900000011',self.password)['user']['id'],account['user']['id'])


if __name__=='__main__':unittest.main()
