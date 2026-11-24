"""Regressões da API após a separação dos módulos."""
import tempfile
import unittest
from pathlib import Path
import httpx
from robot.controller import Controller
from robot.demo_scene import DemoScene
from robot.state import State
from server.src.main import make_app


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = State(Path(self.temp.name), demo=True)
        Controller(self.state, DemoScene(self.state))
        self.app = make_app(self.state)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test')

    async def asyncTearDown(self):
        await self.client.aclose()
        self.state.store.close()
        self.temp.cleanup()

    async def test_dashboard_and_openapi_are_available(self):
        response = await self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/html', response.headers['content-type'])
        schema = (await self.client.get('/openapi.json')).json()
        self.assertIn('/api/control', schema['paths'])
        self.assertIn('ScheduleUpdate', schema['components']['schemas'])

    async def test_invalid_schedule_does_not_modify_persisted_state(self):
        before = dict(self.state.settings)
        for times, days in [(['24:00'], [0]), (['06:00'], [-1]), ([], [0]), (['6:00'], [0])]:
            response = await self.client.put('/api/settings', json=dict(enabled=True, times=times, days=days))
            self.assertEqual(response.status_code, 422)
        self.assertEqual(self.state.settings, before)
        self.assertIsNone(self.state.store.get('schedule', None))

    async def test_valid_schedule_and_pagination(self):
        response = await self.client.put('/api/settings', json=dict(enabled=True, times=['17:00', '06:00', '06:00'], days=[2, 0, 2]))
        self.assertEqual(response.json(), {'ok': True})
        self.assertEqual(self.state.store.get('schedule', None), dict(enabled=True, times=['06:00', '17:00'], days=[0, 2]))
        for query in ['limit=0', 'limit=501', 'offset=-1']:
            self.assertEqual((await self.client.get('/api/inspections?' + query)).status_code, 422)

    async def test_status_is_detached_from_mutable_robot_state(self):
        snapshot = self.state.snapshot()
        self.state.beds[0]['name'] = 'Mudou depois da captura'
        self.assertEqual(snapshot['beds'][0]['name'], 'Canteiro 01')
        self.assertEqual((await self.client.get('/api/status')).json()['beds'][0]['name'], 'Mudou depois da captura')

    async def test_unavailable_controller_returns_conflict(self):
        self.state.controller = None
        response = await self.client.post('/api/control', json={'command': 'START_MISSION'})
        self.assertEqual(response.status_code, 409)
