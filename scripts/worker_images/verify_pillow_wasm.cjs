/** 使用真实 Pyodide/Wasm 运行正式 Pillow，所有输入均为合成图片。 */
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const { loadPyodide } = require(path.resolve('.worker-build/test-runtime/node_modules/pyodide'));

/** 只提供本轮编译的单个 wheel，不接触其他目录或业务数据库。 */
async function main(){
  const output = path.resolve('.worker-build/dist');
  const wheels = fs.readdirSync(output).filter(name => /^pillow-12\.3\.0-cp314-cp314-pyemscripten_2026_0_wasm32\.whl$/.test(name));
  assert.equal(wheels.length, 1, '必须产出指定版本和 ABI 的唯一正式 wheel');
  const bytes = fs.readFileSync(path.join(output, wheels[0]));
  const server = http.createServer((req, res) => {
    // 限定文件名，拒绝路径穿越及任何非本制品请求。
    if (req.url !== '/' + wheels[0]){ res.writeHead(404); res.end(); return; }
    res.writeHead(200, { 'Content-Type': 'application/zip' }); res.end(bytes);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const pyodide = await loadPyodide();
    await pyodide.loadPackage('micropip');
    const micropip = pyodide.pyimport('micropip');
    await micropip.install('http://127.0.0.1:' + server.address().port + '/' + wheels[0]);
    micropip.destroy();
    const result = await pyodide.runPythonAsync(`
import io, json, warnings
import PIL
from PIL import Image, ImageOps, UnidentifiedImageError
assert PIL.__version__ == '12.3.0', PIL.__version__
image = Image.new('RGB', (7, 5), (120, 30, 80))
# 验证正式上传所需 JPEG、PNG、WebP 编解码路径。
for format_name in ('JPEG', 'PNG', 'WEBP'):
    buffer = io.BytesIO()
    image.save(buffer, format=format_name)
    encoded = buffer.getvalue()
    Image.open(io.BytesIO(encoded)).verify()
    decoded = Image.open(io.BytesIO(encoded))
    decoded.load()
    assert decoded.size == (7, 5)
# 验证 EXIF 方向校正与新输出不携带原始元数据。
exif = Image.Exif()
exif[274] = 6
source = io.BytesIO()
image.save(source, format='JPEG', exif=exif)
rotated = ImageOps.exif_transpose(Image.open(io.BytesIO(source.getvalue())))
assert rotated.size == (5, 7)
safe = io.BytesIO()
rotated.convert('RGB').save(safe, format='WEBP')
assert not Image.open(io.BytesIO(safe.getvalue())).getexif()
# 坏图和解压像素上限必须产生可辨认异常。
try:
    Image.open(io.BytesIO(b'not an image')).verify()
    raise AssertionError('坏图被接受')
except UnidentifiedImageError:
    pass
old_limit = Image.MAX_IMAGE_PIXELS
Image.MAX_IMAGE_PIXELS = 16
try:
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        Image.open(io.BytesIO(encoded))
    raise AssertionError('超限图片被接受')
except (Image.DecompressionBombError, Image.DecompressionBombWarning):
    pass
finally:
    Image.MAX_IMAGE_PIXELS = old_limit
json.dumps({'version': PIL.__version__, 'formats': ['JPEG', 'PNG', 'WEBP'], 'exif': True, 'bad_image_rejected': True, 'pixel_limit': True})
`);
    const proof = { ...JSON.parse(result), wheel: wheels[0], sha256: crypto.createHash('sha256').update(bytes).digest('hex') };
    fs.writeFileSync(path.join(output, 'pillow-runtime-verification.json'), JSON.stringify(proof, null, 2));
    console.log(JSON.stringify(proof));
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
