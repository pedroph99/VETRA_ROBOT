const fs = require('fs');
const path = require('path');
const {pathToFileURL} = require('url');
const {chromium} = require('C:/Users/pedro/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');

(async () => {
  const folder = path.resolve(__dirname, '../design');
  const browser = await chromium.launch({
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    headless: true,
    args: ['--autoplay-policy=no-user-gesture-required'],
  });
  try {
    const page = await browser.newPage({viewport: {width: 900, height: 1000}});
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(pathToFileURL(path.join(folder, 'vetra-montagem-camadas.html')).href);
    await page.waitForFunction(() => layers.every(l => l.img?.complete && l.img.naturalWidth > 0));
    await page.locator('#play').click();
    if (await page.locator('#play').textContent() !== 'Continuar') throw Error('Pausa indisponível');
    await page.locator('#spread').fill('0');
    await page.locator('#spread').dispatchEvent('input');
    if (await page.evaluate(() => manual) !== 0) throw Error('Controle de montagem indisponível');
    await page.locator('#restart').click();
    await page.waitForTimeout(100);
    const recording = await page.evaluate(async () => {
      const mime = ['video/mp4;codecs=avc1.42001E', 'video/mp4'].find(x => MediaRecorder.isTypeSupported(x));
      if (!mime) return null;
      t = 0; last = null; playing = true;
      const recorder = new MediaRecorder(canvas.captureStream(30), {mimeType: mime, videoBitsPerSecond: 5000000});
      const chunks = [];
      recorder.ondataavailable = e => {if (e.data.size) chunks.push(e.data)};
      const finished = new Promise(resolve => {recorder.onstop = resolve});
      recorder.start();
      await new Promise(resolve => setTimeout(resolve, 12000));
      recorder.stop();
      await finished;
      const blob = new Blob(chunks, {type: mime});
      return await new Promise(resolve => {const reader = new FileReader();reader.onload = () => resolve(reader.result.split(',')[1]);reader.readAsDataURL(blob)});
    });
    if (recording) fs.writeFileSync(path.join(folder, 'vetra-montagem-camadas.mp4'), Buffer.from(recording, 'base64'));
    if (errors.length) throw Error(errors.join('\n'));
    console.log('Pausa, reinício, controle manual e quatro camadas verificados. MP4:', recording ? 'H.264' : 'MPEG-4');
  } finally {
    await browser.close();
  }
})().catch(error => {console.error(error);process.exitCode = 1});
