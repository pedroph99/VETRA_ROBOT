"""Estado da missão local; compartilhado com a API nesta etapa da migração."""
import math
import threading
from datetime import datetime, timedelta
from pathlib import Path
from copy import deepcopy
from robot.field_layout import HOME, STOP, ROUTE, bed_layout
from robot.energy import return_reserve
from server.src.database import Store
from server.src.config import DATA_DIR

def stamp():
    return datetime.now().astimezone().isoformat(timespec='seconds')

class State:
    def __init__(self, data_dir=DATA_DIR, demo=False):
        self.lock = threading.RLock()
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / 'images').mkdir(exist_ok=True)
        self.store = Store(self.data_dir / 'inspection.sqlite3')
        self.demo = demo
        self.classification_mode = 'legacy'
        self.beds = []
        scenarios = ['normal', 'aphids', 'normal', 'whitefly', 'yellowing', 'normal', 'curling', 'normal']
        crops = ['Alface', 'Tomate', 'Pimentão', 'Alface', 'Tomate', 'Morango', 'Pimentão', 'Alface']
        saved = self.store.get('scenarios', {})
        for i, geometry in enumerate(bed_layout()):
            self.beds.append(dict(id=i+1, name=f'Canteiro {i+1:02}', crop=crops[i%len(crops)],
                                  **geometry, scenario=saved.get(str(i+1), scenarios[i%len(scenarios)]), latest=None))
        for r in self.store.read('inspection', 1000000):
            bed = self.beds[r['bed_id']-1]
            if bed['latest'] is None:
                bed['latest'] = r
        self.settings = self.store.get('schedule', dict(enabled=False, times=['06:00', '17:00'], days=[0,1,2,3,4,5,6]))
        self.fired = self.store.get('fired', [])
        self.status = 'DOCKED'
        self.position = [*HOME]
        self.heading = math.pi/2
        self.battery = 100.
        self.current_bed = None
        self.mission = None
        self.last_mission = next(iter(self.store.read('mission', 1)), None)
        self.error = None
        self.obstacle = False
        self.connected = True
        self.running = True
        self.controller = None

    def log(self, message, level='info'):
        self.store.append('event', dict(time=stamp(), message=message, level=level))

    def next_run(self):
        if not self.settings['enabled']:
            return None
        now = datetime.now().astimezone()
        for offset in range(8):
            day = now + timedelta(days=offset)
            if day.weekday() in self.settings['days']:
                for value in sorted(self.settings['times']):
                    h, m = map(int, value.split(':'))
                    candidate = day.replace(hour=h, minute=m, second=0, microsecond=0)
                    if candidate > now:
                        return candidate.isoformat()
        return None

    def snapshot(self):
        with self.lock:
            counts = {key: sum((b['latest'] or {}).get('status', 'PENDING') == key for b in self.beds) for key in ['NORMAL','SUSPECT','ALERT','PENDING']}
            return deepcopy(dict(version='inspection-1', beds=self.beds, robot_status=self.status, current_bed=self.current_bed,
                        position=self.position, heading=self.heading, battery=round(self.battery,1), mission=self.mission,
                        return_reserve=round(max(20., return_reserve(self.controller.route_distance if self.controller else 0.)), 1),
                        counts=counts, events=self.store.read('event',60), settings=self.settings, next_run=self.next_run(),
                        last_mission=self.last_mission, demo=self.demo, classification_mode=self.classification_mode, connected=self.connected, error=self.error,
                        obstacle=self.obstacle, route=ROUTE, start=HOME, stop=STOP, server_time=stamp()))
