"""Inicialização conjunta do robô simulado e sua API local."""
import argparse
import json
import signal
import threading
import time
import webbrowser
from pathlib import Path
import uvicorn
from robot.state import State
from robot.controller import Controller
from robot.demo_scene import DemoScene
from robot.inference_client import HttpDetector
from server.src.classification.model import Classifier
from server.src.main import make_app
from server.src.config import DATA_DIR, SCENES_DIR

def main():
    parser = argparse.ArgumentParser(description='AgroBot · Inspeção fitossanitária em estufas')
    parser.add_argument('--demo', action='store_true', help='Demonstração sem CoppeliaSim; fotos PlantVillage e inferência real')
    parser.add_argument('--web-host', default='127.0.0.1')
    parser.add_argument('--web-port', type=int, default=8000)
    parser.add_argument('--coppelia-host', default='127.0.0.1')
    parser.add_argument('--coppelia-port', type=int, default=23000)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--no-save-scene', action='store_true')
    parser.add_argument('--scene-path', default=str(SCENES_DIR/'AgroBotEstufa.ttt'))
    parser.add_argument('--data-dir', type=Path, default=DATA_DIR)
    parser.add_argument('--inference-url', help='Servidor de modelo externo; padrão: API local na porta do painel')
    parser.add_argument('--crops', type=Path, default=Path(__file__).parent / 'crops.json')
    parser.add_argument('--legacy-demo', action='store_true', help='Apenas testes antigos: resultados artificiais sem modelo')
    args = parser.parse_args()
    state = State(args.data_dir, args.demo)
    crop_map = json.loads(args.crops.read_text(encoding='utf-8'))
    for bed in state.beds:
        crop = crop_map.get(str(bed['id']), bed['crop'])
        if not isinstance(crop, str) or not crop.strip():
            raise ValueError('Cultura inválida no arquivo de canteiros.')
        bed['crop'] = crop
    classifier = None
    detector = None
    if not args.legacy_demo:
        detector = HttpDetector(args.inference_url or f'http://127.0.0.1:{args.web_port}')
        if not args.inference_url:
            print('Carregando o modelo PlantVillage em CPU...', flush=True)
            classifier = Classifier()
            classifier.load()
        state.classification_mode = 'model'
    if args.demo:
        scene = DemoScene(state)
    else:
        from robot.greenhouse_scene import Scene
        scene = Scene(state, args)
    controller = Controller(state, scene, detector)
    state.log('Sistema de inspeção iniciado. ' + ('Resultados artificiais (modo legado).' if args.legacy_demo else 'Folha de referência por cultura; a captura visível é enviada à inferência HTTP. Cultura não suportada fica sem diagnóstico.'))
    server = uvicorn.Server(uvicorn.Config(make_app(state, classifier), host=args.web_host, port=args.web_port, log_level='warning'))
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()
    def stop(*_):
        state.running = False
        server.should_exit = True
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    if not args.no_browser:
        threading.Timer(1, lambda: webbrowser.open(f'http://{args.web_host}:{args.web_port}')).start()
    print(f'AgroBot · Inspeção: http://{args.web_host}:{args.web_port}', flush=True)
    last = time.monotonic()
    try:
        while state.running and not server.should_exit:
            now = time.monotonic()
            with state.lock:
                try:
                    controller.tick(min(now-last, .2))
                except Exception as exc:
                    state.status, state.connected, state.error = 'ERROR', False, 'SIMULATOR_CONNECTION'
                    state.log(f'Comunicação com o simulador interrompida: {exc}', 'error')
            last = now
            time.sleep(.05)
    finally:
        stop()
        controller.close()
        if not args.demo:
            scene.close()
        server_thread.join(timeout=10)
        if not server_thread.is_alive():
            state.store.close()

if __name__ == '__main__':
    main()
