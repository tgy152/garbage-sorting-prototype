/**
 * 把大屏打包成「单个 html」：
 *   css、我们的 js、three.js、echarts 全部内联进去。
 *
 * 用处：有些机器上双击 index.html 会因为相对路径、目录权限、
 * 或者被别的软件接管 .html 关联而打不开；单文件版只有一份文件，
 * 挪到哪、发给谁都能直接双击打开，断网也不受影响。
 *
 * 用法（在 大屏 目录下）：node build-single.mjs
 */

import { readFileSync, writeFileSync, statSync } from 'node:fs';
import { resolve } from 'node:path';

const read = (p) => readFileSync(resolve(p), 'utf8');

// 内联进 <script> 的代码里如果出现 </script> 会提前结束脚本块，统一转义
const safe = (code) => code.replace(/<\/script/gi, '<\\/script');

const html = read('index.html');
const css = read('screen.css');
const js = read('screen.js');
const scene = read('scene3d.js');
const three = read('vendor/three.min.js');
const echarts = read('vendor/echarts.min.js');

let out = html;

out = out.replace(
  '<link rel="stylesheet" href="screen.css">',
  '<style>\n' + css + '\n</style>'
);
out = out.replace(
  '<script src="vendor/three.min.js"></script>',
  '<script>\n' + safe(three) + '\n</script>'
);
out = out.replace(
  '<script src="vendor/echarts.min.js"></script>',
  '<script>\n' + safe(echarts) + '\n</script>'
);
out = out.replace(
  '<script src="screen.js"></script>',
  '<script>\n' + safe(js) + '\n</script>'
);
out = out.replace(
  '<script src="scene3d.js"></script>',
  '<script>\n' + safe(scene) + '\n</script>'
);

const target = resolve('数据大屏-单文件版.html');
writeFileSync(target, out, 'utf8');

console.log(
  '已生成 数据大屏-单文件版.html，' +
  (statSync(target).size / 1024 / 1024).toFixed(2) + ' MB'
);
