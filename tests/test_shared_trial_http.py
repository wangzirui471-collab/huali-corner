"""Independent HTTP clients share one backend's persisted products and orders."""
import base64
import io
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))
from server import make_server


class SharedTrialHttpTests(unittest.TestCase):
    def test_clients_share_listing_order_photo_and_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            server = None

            def start():
                instance = make_server(directory, 0, trial=True)
                threading.Thread(target=instance.serve_forever, daemon=True).start()
                return instance

            # Separate request clients, like browsers on different computers.
            seller_client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            buyer_client = urllib.request.build_opener(urllib.request.ProxyHandler({}))

            def request(client, path, payload=None, token=None):
                base = 'http://127.0.0.1:' + str(server.server_port)
                headers = {'Content-Type': 'application/json', 'Origin': base}
                if token:
                    headers['Authorization'] = 'Bearer ' + token
                data = json.dumps(payload).encode() if payload is not None else None
                with client.open(urllib.request.Request(base + path, data=data, headers=headers), timeout=10) as response:
                    return response.read()

            def api(client, path, payload=None, token=None):
                return json.loads(request(client, '/api' + path, payload, token))

            try:
                server = start()
                seller = api(seller_client, '/auth/register', {'phone': '13922220001', 'password': 'SyntheticOnly2026!', 'nickname': '共享卖家'})
                buyer = api(buyer_client, '/auth/register', {'phone': '13922220002', 'password': 'SyntheticOnly2026!', 'nickname': '共享买家'})
                photos = []
                for angle, color in [('front', 'red'), ('side', 'green'), ('top', 'blue')]:
                    photo = io.BytesIO()
                    Image.new('RGB', (100, 100), color).save(photo, 'PNG')
                    uploaded = api(seller_client, '/upload', {'angle': angle, 'content': base64.b64encode(photo.getvalue()).decode()}, seller['token'])
                    photos.append(uploaded['id'])
                product = api(seller_client, '/publish', {'title': '共享测试台灯', 'description': '用于验证共享后端，非真实出售', 'category': 'living', 'price': 1200, 'delivery_fee': 0, 'delivery': 'pickup', 'region': 'A1楼下', 'photos': photos}, seller['token'])
                pid = product['id']
                products = api(buyer_client, '/products')
                self.assertIn(pid, [item['id'] for item in products])
                photo_url = api(buyer_client, '/product?id=' + str(pid))['photos'][0]['url']
                original_photo = request(buyer_client, photo_url)
                self.assertGreater(len(original_photo), 0)
                order = api(buyer_client, '/checkout', {'product_ids': [pid], 'delivery': 'pickup', 'appointment': time.time() + 7200, 'key': 'shared-http'}, buyer['token'])
                api(buyer_client, '/order/action', {'id': order['id'], 'action': 'pay'}, buyer['token'])
                self.assertIn(order['id'], [item['id'] for item in api(seller_client, '/orders', token=seller['token'])])
                self.assertGreater(api(seller_client, '/notifications', token=seller['token'])['unread'], 0)
                server.shutdown()
                server.server_close()
                server = None
                server = start()
                self.assertEqual(api(buyer_client, '/product?id=' + str(pid))['id'], pid)
                self.assertEqual(api(seller_client, '/order?id=' + str(order['id']), token=seller['token'])['status'], 'paid')
                self.assertEqual(request(buyer_client, photo_url), original_photo)
                self.assertTrue((Path(directory) / 'market.sqlite3').is_file())
            finally:
                if server:
                    server.shutdown()
                    server.server_close()


if __name__ == '__main__':
    unittest.main()
