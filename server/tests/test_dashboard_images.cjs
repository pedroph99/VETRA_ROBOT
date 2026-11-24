const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '../templates/dashboard.html'), 'utf8');
const script = html.match(/<script[^>]*>([\s\S]*?)<\/script>/)[1];
new Function(script); // Verifica também a sintaxe de todo o painel.
const helper = script.slice(script.indexOf('function recordImages('), script.indexOf('function recordDetail('));
const context = vm.createContext({esc: value => String(value).replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;')});
vm.runInContext(helper, context);
const current = context.recordImages({image: '/images/modelo.jpg', camera_image: '/images/camera.png', image_source: 'plantvillage'});
assert.ok(current.includes('Captura do robô'));
assert.ok(current.includes('Foto enviada ao YOLO'));
assert.ok(current.includes('src="/images/modelo.jpg"'));
assert.ok(current.includes('src="/images/camera.png"'));
assert.ok(!current.includes('<details>')); // As duas fotos ficam visíveis ao abrir.
for (const record of [{image: '/images/old.svg', simulated: true}, {image: '/images/alface.png', analysis_state: 'unsupported_crop'}]) {
  const result = context.recordImages(record);
  assert.equal((result.match(/<img /g) || []).length, 1);
  assert.ok(result.includes('Nenhuma imagem foi enviada ao YOLO'));
}
const same = context.recordImages({image: '/images/capture.jpg', camera_image: '/images/capture.jpg', analysis_image: '/images/capture.jpg'});
assert.equal((same.match(/<img /g) || []).length, 1);
assert.ok(same.includes('Captura analisada'));
const scene = context.recordImages({image: '/images/crop.jpg', camera_image: '/images/scene.png', analysis_image: '/images/crop.jpg', image_source: 'coppeliasim'});
assert.ok(scene.includes('Recorte enviado ao YOLO'));
const unsafe = context.recordImages({image: '/images/"<test>.png'});
assert.ok(unsafe.includes('&quot;&lt;test>'));
console.log('OK: captura e recorte visíveis, imagem única no demo e escape de URLs.');
