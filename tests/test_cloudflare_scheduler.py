import importlib
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from cloudflare_test_support import CloudCase

class SchedulerTests(CloudCase):
    async def test_worker_scheduled_runs_trade_maintenance(self):
        with patch.object(sys.modules['workers'], 'WorkerEntrypoint', object, create=True):
            worker = importlib.import_module('app.cloudflare.worker')
        job = AsyncMock(return_value={'ok': True, 'processed': 0})
        fake = SimpleNamespace(cf_trade_tick=job)
        entry = worker.Default()
        entry.env = SimpleNamespace(DB='local-only', MEDIA='local-only')
        with patch.object(worker, 'Api', return_value=fake):
            await entry.scheduled(SimpleNamespace(scheduledTime=100000), entry.env, None)
        job.assert_awaited_once_with()
