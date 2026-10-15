import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import make_server


class PublishingHttpTests(unittest.TestCase):
    def test_draft_routes_preserve_version_and_account_boundary(self):
        with tempfile.TemporaryDirectory() as root:
            server = make_server(root, 0)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                tokens = []
                for phone in ['13800000031', '13800000032']:
                    code = server.market.request_code(phone)['demo_code']
                    tokens.append(server.market.login(phone, code)['token'])

                def request(path, token, data=None):
                    req = urllib.request.Request(
                        f'http://127.0.0.1:{server.server_port}/api{path}',
                        data=json.dumps(data).encode() if data is not None else None,
                        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
                    )
                    try:
                        with urllib.request.urlopen(req) as response:
                            return response.status, json.loads(response.read())
                    except urllib.error.HTTPError as error:
                        return error.code, json.loads(error.read())

                status, draft = request('/draft', tokens[0], {'version': 0, 'fields': {'title': 'HTTP草稿'}})
                self.assertEqual(status, 200, draft)
                self.assertEqual(request('/draft?id=' + draft['id'], tokens[1])[0], 404)
                self.assertEqual(request('/drafts', tokens[1])[1], [])
                self.assertEqual(request('/drafts', tokens[0])[1][0]['fields']['title'], 'HTTP草稿')
                status, _ = request('/draft', tokens[0], {'id': draft['id'], 'version': 0, 'fields': {'title': '旧版'}})
                self.assertEqual(status, 409)
                self.assertEqual(request('/draft/publish', tokens[0], {'id': draft['id'], 'version': 1})[0], 400)
                self.assertEqual(request('/draft/delete', tokens[0], {'id': draft['id']})[0], 200)
                self.assertEqual(request('/drafts', tokens[0])[1], [])
            finally:
                server.shutdown()
                server.server_close()
