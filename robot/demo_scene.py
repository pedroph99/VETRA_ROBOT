"""Câmera ilustrativa para demonstração sem CoppeliaSim."""
from robot.field_layout import HOME
from robot.capture_plan import prepare_reference

class DemoScene:
    home = HOME
    def __init__(self, state):
        self.state = state

    def move(self, x, y, heading):
        pass

    def blocked(self, x, y, heading):
        return self.state.obstacle

    def aim(self, bed):
        pass

    def capture(self, bed, key):
        # Explicitly illustrative evidence for browser-only demonstrations.
        leaves = ''.join(f'<ellipse cx="{x}" cy="{y}" rx="48" ry="22" transform="rotate({a} {x} {y})" fill="{c}" stroke="#77a66c" stroke-width="2"/>' for x,y,a,c in [(170,210,-35,'#326e45'),(240,165,30,'#418752'),(325,230,-25,'#356e43'),(375,150,25,'#568b46'),(265,280,30,'#467c48')])
        marks = ''
        if bed['scenario'] in ('aphids','whitefly'):
            color = '#e8edda' if bed['scenario']=='whitefly' else '#182f20'
            marks = ''.join(f'<ellipse cx="{238+i*11}" cy="{158+(i%3)*9}" rx="4" ry="3" fill="{color}"/>' for i in range(8))
        elif bed['scenario'] in ('yellowing','curling'):
            marks = '<path d="M140 210 Q170 175 210 194 Q180 240 140 210" fill="#c6b954"/>'
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="640" height="400" viewBox="0 0 640 400"><rect width="640" height="400" fill="#172c23"/><path d="M280 390 Q290 220 330 80" stroke="#769858" stroke-width="9" fill="none"/>{leaves}{marks}<rect x="18" y="18" width="604" height="364" rx="12" stroke="#8bab8f" fill="none"/><text x="34" y="48" fill="#eee" font-family="sans-serif" font-size="15">CANTEIRO {bed["id"]:02} · IMAGEM ILUSTRATIVA</text><text x="34" y="359" fill="#bbcdbb" font-family="sans-serif" font-size="13">Demonstração sem câmera • classificação simulada</text></svg>'
        path = self.state.data_dir / 'images' / f'{key}.svg'
        path.write_text(svg, encoding='utf-8')
        return path.name, 'illustration'

    def capture_for_model(self, bed, key, bank):
        reference = prepare_reference(bank, bed['crop'])
        if reference is None:
            filename, source = self.capture(bed, key)
            return dict(filename=filename, source=source, analysis_file=None,
                        analysis_state='unsupported_crop')
        if reference['image'] is None:
            filename, source = self.capture(bed, key)
            return dict(filename=filename, source=source, analysis_file=None,
                        analysis_state='poor_quality', capture_conditions=reference['conditions'],
                        capture_quality=reference['quality'], capture_attempts=reference['attempts'])
        path = self.state.data_dir / 'images' / f'{key}.jpg'
        reference['image'].save(path, format='JPEG', quality=90)
        return dict(filename=path.name, source='plantvillage', analysis_file=path.name,
                    analysis_state='ready', capture_conditions=reference['conditions'],
                    capture_quality=reference['quality'], capture_attempts=reference['attempts'],
                    photo_provenance=reference['provenance'])

    def update(self):
        pass
