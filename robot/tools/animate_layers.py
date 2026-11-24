"""Animate the generated transparent robot assembly sprites."""
import base64
import io
import json
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1] / 'design'
SIZE = (1000, 1120)
FPS, DURATION = 15, 12


def font(size, bold=False):
    name = 'arialbd.ttf' if bold else 'arial.ttf'
    return ImageFont.truetype(str(Path('C:/Windows/Fonts') / name), size)


def ease(value):
    value = max(0, min(1, value))
    return value*value*(3-2*value)


def expansion(t):
    if t < 1.2:
        return 1.
    if t < 4.7:
        return 1-ease((t-1.2)/3.5)
    if t < 6.3:
        return 0.
    if t < 9.8:
        return ease((t-6.3)/3.5)
    return 1.


def main():
    source = Image.open(ROOT / 'vetra-camadas-animacao-sprites.png').convert('RGBA')
    array = np.asarray(source)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        (array[:, :, 3] > 24).astype('uint8'))
    objects = sorted((i for i in range(1, count) if stats[i, 4] > 10000),
                     key=lambda i: stats[i, 1])
    assert len(objects) == 4, 'São necessárias quatro camadas separadas.'
    names = ['Câmera e suporte', 'Carcaça e sensores', 'Eletrônica e alimentação', 'Chassi e tração']
    expanded = [140, 325, 580, 770]
    assembled = [570, 675, 735, 770]
    layers = []
    for i, component in enumerate(objects):
        x, y, w, h, _ = stats[component]
        sprite = array[y:y+h, x:x+w].copy()
        selection = (labels[y:y+h, x:x+w] == component).astype('uint8')
        # A small mask border retains the original antialiased alpha edges.
        selection = cv2.dilate(selection, np.ones((3, 3), np.uint8))
        sprite[:, :, 3] *= selection
        image = Image.fromarray(sprite).resize((round(w*.5), round(h*.5)), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        image.save(buf, format='PNG')
        layers.append(dict(name=names[i], x=round(278+x*.5), image=image,
                           expanded=expanded[i], assembled=assembled[i],
                           src='data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode()))

    def draw_frame(t):
        spread = expansion(t)
        im = Image.new('RGBA', SIZE, '#f7f9f8')
        d = ImageDraw.Draw(im)
        d.text((56, 35), 'VETRA', font=font(37, True), fill='#063b40')
        d.text((56, 84), 'Montagem por camadas', font=font(24), fill='#3d6466')
        d.line((56, 122, 944, 122), fill='#d8e7e1', width=2)
        # Constant ground shadow, with the lower chassis stationary.
        d.ellipse((310, 1000, 720, 1028), fill='#e4e9e6')
        positions = []
        for i, layer in enumerate(layers):
            # Assemble bottom to top; reverse the sequence when exploding.
            s = ease(max(0, min(1, spread*1.18-i*.06))) if i < 3 else 1
            y = round(layer['assembled']+(layer['expanded']-layer['assembled'])*s)
            positions.append(y)
        for i in [3, 2, 1, 0]:
            layer = layers[i]
            zoom = 1+.35*(1-spread)
            sprite = layer['image'].resize((round(layer['image'].width*zoom),
                                           round(layer['image'].height*zoom)), Image.Resampling.LANCZOS)
            im.alpha_composite(sprite, (round(500+(layer['x']-500)*zoom),
                                       round(1020+(positions[i]-1020)*zoom)))
        if spread > .5:
            overlay = Image.new('RGBA', SIZE)
            od = ImageDraw.Draw(overlay)
            opacity = round(255*ease((spread-.5)/.5))
            for i, layer in enumerate(layers):
                y = positions[i]+layer['image'].height//2
                od.line((695, y, 747, y), fill=(27, 144, 129, opacity), width=2)
                od.ellipse((750, y-13, 776, y+13), fill=(8, 131, 116, opacity))
                od.text((758, y-9), str(i+1), font=font(16, True), fill=(255,255,255,opacity))
                words = layer['name'].split(' e ')
                od.text((790, y-19), words[0], font=font(17, True), fill=(6, 59, 64, opacity))
                if len(words)>1:
                    od.text((790, y+4), 'e '+words[1], font=font(17), fill=(6, 59, 64, opacity))
            im = Image.alpha_composite(im, overlay)
        d = ImageDraw.Draw(im)
        status = 'Vista em camadas' if spread > .98 else 'Robô montado' if spread < .02 else 'Montando' if t < 6.3 else 'Separando as camadas'
        d.rounded_rectangle((56, 1054, 365, 1097), radius=20, fill='#067e71')
        d.text((76, 1064), status, font=font(20, True), fill='white')
        d.text((612, 1071), 'Animação conceitual · ciclo de 12 s', font=font(16), fill='#58706d')
        return im.convert('RGB').resize((800, 896), Image.Resampling.LANCZOS)

    frames = [draw_frame(i/FPS) for i in range(FPS*DURATION)]
    palette = frames[0].quantize(colors=256)
    gif_frames = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
    gif_path = ROOT/'vetra-montagem-camadas.gif'
    gif_frames[0].save(gif_path, save_all=True, append_images=gif_frames[1:],
                       duration=[70 if i%3 else 60 for i in range(len(frames))], loop=0,
                       optimize=False, disposal=1)
    video_path = ROOT/'vetra-montagem-camadas.mp4'
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*'mp4v'), FPS, (800,896))
    if not writer.isOpened():
        raise RuntimeError('Não foi possível criar o vídeo.')
    for frame in frames:
        writer.write(cv2.cvtColor(np.asarray(frame), cv2.COLOR_RGB2BGR))
    writer.release()
    for name, second in [('explodido',0),('montado',5.5)]:
        draw_frame(second).save(ROOT/f'vetra-animacao-{name}-preview.png')
    metadata = [{k:v for k,v in layer.items() if k != 'image'} for layer in layers]
    template = (Path(__file__).with_name('layers_animation_template.html')).read_text(encoding='utf-8')
    (ROOT/'vetra-montagem-camadas.html').write_text(template.replace('__LAYERS_JSON__',json.dumps(metadata,ensure_ascii=False)),encoding='utf-8')
    with Image.open(gif_path) as check:
        assert check.n_frames > 70 and check.info['loop'] == 0
        duration = 0
        for i in range(check.n_frames):
            check.seek(i)
            duration += check.info['duration']
        assert duration == DURATION*1000, duration
    capture = cv2.VideoCapture(str(video_path))
    assert int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) == FPS*DURATION
    capture.release()
    print('GIF, MP4 e animação interativa salvos em', ROOT)


if __name__ == '__main__':
    main()
