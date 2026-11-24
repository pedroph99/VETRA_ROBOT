import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from fastapi.testclient import TestClient
from robot.state import State
from robot.controller import Controller
from robot.demo_scene import DemoScene
from server.src.main import make_app
from robot.field_layout import STOP, HOME

class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.s = State(Path(self.temp.name), demo=True)
        self.c = Controller(self.s, DemoScene(self.s))
        self.api = TestClient(make_app(self.s))

    def tearDown(self):
        self.api.close()
        self.s.store.db.close()
        self.temp.cleanup()

    def finish(self):
        for _ in range(4000):
            self.c.tick(.1)
            if self.s.status in ('DOCKED','FINISHED'):
                return
        self.fail('Mission did not finish')

    def test_full_mission_records_and_persistence(self):
        self.assertEqual(self.s.snapshot()['counts']['PENDING'],12)
        self.c.command('START_MISSION')
        self.finish()
        records = self.s.store.read('inspection')
        self.assertEqual(len(records),12)
        self.assertEqual({r['bed_id'] for r in records},set(range(1,13)))
        self.assertEqual(self.s.position,list(STOP))
        self.assertEqual(self.s.snapshot()['counts'],dict(NORMAL=6,SUSPECT=2,ALERT=4,PENDING=0))
        for r in records:
            self.assertEqual(self.api.get(r['image']).status_code,200)
            self.assertTrue(r['simulated'])
        self.c.command('RETURN_HOME'); self.finish()
        self.assertEqual(self.s.position,list(HOME))
        self.c.command('START_MISSION')
        self.finish()
        self.assertEqual(len(self.s.store.read('inspection')),24)
        loaded = State(Path(self.temp.name),demo=True)
        self.assertEqual(loaded.snapshot()['counts']['PENDING'],0)
        self.assertEqual(loaded.last_mission['outcome'],'COMPLETED')
        loaded.store.db.close()

    def test_pause_and_abort(self):
        self.c.command('START_MISSION')
        self.c.tick(.1)
        self.c.command('PAUSE_MISSION')
        before=list(self.s.position)
        self.c.tick(2)
        self.assertEqual(self.s.position,before)
        self.c.command('RESUME_MISSION')
        self.c.tick(.1)
        self.c.command('RETURN_HOME')
        self.finish()
        self.assertEqual(self.s.last_mission['outcome'],'INTERRUPTED')

    def test_u_route_and_return_do_not_cut_through_middle_beds(self):
        import math
        poses = []
        self.c.scene.move = lambda x,y,h: poses.append((x,y))
        self.c.command('START_MISSION'); self.finish()
        outward = list(poses)
        self.assertGreater(max(y for x,y in outward),6.)
        self.assertTrue(all(y>4.1 for x,y in outward if abs(x)<1.5))
        self.assertTrue(all(math.dist(a,b)<.3 for a,b in zip(outward,outward[1:])))
        poses.clear()
        self.c.command('RETURN_HOME'); self.finish()
        self.assertGreater(max(y for x,y in poses),6.)
        self.assertTrue(all(y>4.1 for x,y in poses if abs(x)<1.5))
        self.assertEqual(self.s.status,'DOCKED')

    def test_obstacle_stops_then_resumes(self):
        self.c.command('START_MISSION')
        self.s.obstacle=True
        before=list(self.s.position)
        for _ in range(120): self.c.tick(.1)
        self.assertEqual(self.s.status,'BLOCKED')
        self.assertEqual(self.s.position,before)
        self.s.obstacle=False
        self.finish()
        self.assertEqual(self.s.last_mission['outcome'],'COMPLETED')

    def test_low_battery_returns_and_recharges(self):
        self.c.command('START_MISSION')
        self.c.tick(1)
        self.s.battery=19
        self.finish()
        self.assertEqual(self.s.last_mission['outcome'],'LOW_BATTERY')
        before=self.s.battery
        self.c.tick(1)
        self.assertGreater(self.s.battery,before)

    def test_movement_uses_more_energy_than_waiting(self):
        self.c.command('START_MISSION')
        self.s.status = 'PAUSED'
        before = self.s.battery
        self.c.tick(1)
        paused_cost = before - self.s.battery
        self.s.status = 'NAVIGATING'
        self.c.tick(1)
        moving_cost = before - paused_cost - self.s.battery
        self.assertGreater(moving_cost, paused_cost)

    def test_return_reserve_increases_with_distance(self):
        at_base = self.s.snapshot()['return_reserve']
        self.c.command('START_MISSION')
        self.c.route_distance = 25
        self.s.battery = 21
        self.assertGreater(self.s.snapshot()['return_reserve'], at_base)
        self.c.tick(.1)
        self.assertEqual(self.s.status, 'RETURNING_HOME')
        self.assertEqual(self.s.mission['outcome'], 'LOW_BATTERY')

    def test_scheduler_once_per_slot(self):
        now=datetime.now().astimezone()
        self.s.settings=dict(enabled=True,days=[now.weekday()],times=[now.strftime('%H:%M')])
        self.c.schedule(now)
        first=self.s.mission['id']
        self.c.schedule(now)
        self.assertEqual(self.s.mission['id'],first)
        self.assertEqual(len(self.s.fired),1)
        self.finish()
        self.c.schedule(now)
        self.assertIsNone(self.s.mission)

    def test_validation_filters_and_export(self):
        self.assertEqual(self.api.put('/api/settings',json=dict(enabled=True,days=[8],times=['25:00'])).status_code,422)
        self.assertEqual(self.api.post('/api/control',json={'command':'RESUME_MISSION'}).status_code,409)
        self.assertEqual(self.api.put('/api/beds/99/scenario',json={'scenario':'normal'}).status_code,404)
        self.assertEqual(self.api.post('/api/control',json={'command':'START_MISSION'}).status_code,200)
        self.assertEqual(self.api.post('/api/control',json={'command':'START_MISSION'}).status_code,409)
        self.finish()
        rows=self.api.get('/api/inspections?bed_id=2&status=ALERT').json()
        self.assertEqual(rows['total'],1)
        self.assertEqual(rows['items'][0]['confidence'],.93)
        self.assertIn('text/csv',self.api.get('/api/export').headers['content-type'])
        self.assertEqual(self.api.get('/api/inspections?limit=0').status_code,422)

    def test_scenario_only_changes_future_results(self):
        self.c.command('START_MISSION'); self.finish()
        old=self.s.beds[1]['latest']['id']
        self.api.put('/api/beds/2/scenario',json={'scenario':'normal'})
        self.assertEqual(self.s.beds[1]['latest']['status'],'ALERT')
        self.c.command('RETURN_HOME'); self.finish()
        self.c.command('START_MISSION'); self.finish()
        self.assertEqual(self.s.beds[1]['latest']['status'],'NORMAL')
        self.assertTrue(any(r['id']==old for r in self.s.store.read('inspection')))

    def test_camera_failure_never_records_false_success(self):
        def fail(*args): raise RuntimeError('camera offline')
        self.c.scene.capture=fail
        self.c.command('START_MISSION')
        for _ in range(100): self.c.tick(.1)
        self.assertEqual(self.s.status,'ERROR')
        self.assertEqual(self.s.error,'CAMERA_UNAVAILABLE')
        self.assertEqual(self.s.store.read('inspection'),[])

    def test_capture_waits_for_camera_alignment(self):
        aligned = False
        self.c.scene.advance_camera = lambda dt, tracking: not tracking or aligned
        self.c.command('START_MISSION')
        for _ in range(100):
            self.c.tick(.1)
            if self.s.status == 'INSPECTING':
                break
        self.assertEqual(self.s.status, 'INSPECTING')
        for _ in range(30):
            self.c.tick(.1)
        self.assertEqual(self.s.status, 'INSPECTING')
        self.assertEqual(list((self.s.data_dir/'images').iterdir()), [])
        aligned = True
        self.c.tick(.1)
        self.assertEqual(len(self.s.store.read('inspection')), 1)

if __name__ == '__main__': unittest.main(verbosity=2)
