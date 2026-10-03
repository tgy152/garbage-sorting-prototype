/* ==========================================================================
   Three.js 三维拆解动画

   这段代码整块包在 try/catch 里：浏览器没启用 WebGL、显卡驱动异常、
   或者 three.js 没加载成功时，只把 __scene3dOk 置成 false 就退出，
   数据面板和四个部件小卡由 screen.js 照常工作，页面不会白屏。
   ========================================================================== */

(function () {
  if (typeof THREE === 'undefined') {
    window.__scene3dOk = false;
    window.__scene3dError = 'three.js 未加载';
    return;
  }

  try {
    const canvas = document.getElementById('gl');
    const labelLayer = document.getElementById('labels');

    const renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0B0E08);
    scene.fog = new THREE.Fog(0x0B0E08, 13, 27);

    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
    const CAM_HOME = new THREE.Vector3(0, 4.05, 8.8);
    const CAM_LOOK = new THREE.Vector3(0, 2.02, 0.9);
    camera.position.copy(CAM_HOME);
    camera.lookAt(CAM_LOOK);

    scene.add(new THREE.HemisphereLight(0xE8DCC7, 0x161A11, 0.75));
    const keyLight = new THREE.DirectionalLight(0xFFF3DC, 0.85);
    keyLight.position.set(5, 9, 6);
    scene.add(keyLight);
    const rimOchre = new THREE.PointLight(0xC08E3A, 0.85, 22);
    rimOchre.position.set(-6.5, 4.2, -3.6);
    scene.add(rimOchre);
    const rimBlue = new THREE.PointLight(0x4E86BE, 0.5, 20);
    rimBlue.position.set(6.5, 3.4, -3.0);
    scene.add(rimBlue);

    // 地面：圆盘 + 网格 + 一圈赭石描边
    const stageDisc = new THREE.Mesh(
      new THREE.CircleGeometry(7.4, 64),
      new THREE.MeshBasicMaterial({ color: 0x14180F })
    );
    stageDisc.rotation.x = -Math.PI / 2;
    scene.add(stageDisc);

    const edgeRing = new THREE.Mesh(
      new THREE.RingGeometry(6.05, 6.14, 96),
      new THREE.MeshBasicMaterial({
        color: 0xC08E3A, transparent: true, opacity: 0.28, side: THREE.DoubleSide,
      })
    );
    edgeRing.rotation.x = -Math.PI / 2;
    edgeRing.position.y = 0.012;
    scene.add(edgeRing);

    const grid = new THREE.GridHelper(13, 26, 0x2C3423, 0x1B2016);
    grid.position.y = 0.008;
    scene.add(grid);

    /* ---- 四个桶 ---- */

    const bins = BINS.map(function (b) {
      const color = new THREE.Color(BIN_COLOR[b.key]);
      const g = new THREE.Group();

      const body = new THREE.Mesh(
        new THREE.CylinderGeometry(0.66, 0.72, 1.0, 28, 1, true),
        new THREE.MeshStandardMaterial({
          color: color, metalness: 0.22, roughness: 0.46,
          transparent: true, opacity: 0.92, side: THREE.DoubleSide,
        })
      );
      body.position.y = 0.5;
      g.add(body);

      const mouth = new THREE.Mesh(
        new THREE.CircleGeometry(0.64, 28),
        new THREE.MeshBasicMaterial({ color: color, transparent: true, opacity: 0.34 })
      );
      mouth.rotation.x = -Math.PI / 2;
      mouth.position.y = 1.0;
      g.add(mouth);

      const band = new THREE.Mesh(
        new THREE.TorusGeometry(0.665, 0.035, 8, 40),
        new THREE.MeshBasicMaterial({ color: color, transparent: true, opacity: 0.85 })
      );
      band.rotation.x = -Math.PI / 2;
      band.position.y = 1.0;
      g.add(band);

      const glow = new THREE.Mesh(
        new THREE.RingGeometry(0.74, 0.86, 40),
        new THREE.MeshBasicMaterial({
          color: color, transparent: true, opacity: 0.18, side: THREE.DoubleSide,
        })
      );
      glow.rotation.x = -Math.PI / 2;
      glow.position.y = 0.02;
      g.add(glow);

      g.position.set(b.x, 0, b.z);
      scene.add(g);

      return {
        key: b.key, x: b.x, z: b.z,
        group: g, mouth: mouth, band: band, glow: glow,
      };
    });

    /* ---- 奶茶的四个部件：用基础几何体搭，不依赖外部模型 ---- */

    // 杯体是半透明塑料，只靠反射在深色底上会看不清，给它一点自发光
    const PLASTIC = {
      color: 0xD6E2E6, metalness: 0.05, roughness: 0.16,
      transparent: true, opacity: 0.56,
      emissive: 0x1D2A30, emissiveIntensity: 0.9,
      side: THREE.DoubleSide,
    };
    const SOLID = {
      color: 0xCBD8DE, metalness: 0.08, roughness: 0.3,
      emissive: 0x1A2429, emissiveIntensity: 0.6,
    };

    function makeLiquid() {
      const g = new THREE.Group();
      const juice = new THREE.Mesh(
        new THREE.SphereGeometry(0.3, 24, 18),
        new THREE.MeshStandardMaterial({ color: 0x9AAB5C, roughness: 0.35, metalness: 0.05 })
      );
      juice.scale.set(1, 0.72, 1);
      juice.position.y = -0.04;
      g.add(juice);
      const pearlMat = new THREE.MeshStandardMaterial({ color: 0x4A3A22, roughness: 0.55 });
      [[0.12, -0.13, 0.06], [-0.11, -0.12, -0.05], [0.01, -0.17, 0.13]].forEach(function (p) {
        const pearl = new THREE.Mesh(new THREE.SphereGeometry(0.062, 12, 10), pearlMat);
        pearl.position.set(p[0], p[1], p[2]);
        g.add(pearl);
      });
      return g;
    }

    function makeBody() {
      const g = new THREE.Group();
      const cup = new THREE.Mesh(
        new THREE.CylinderGeometry(0.42, 0.33, 1.18, 30, 1, true),
        new THREE.MeshStandardMaterial(PLASTIC)
      );
      g.add(cup);
      const bottom = new THREE.Mesh(
        new THREE.CircleGeometry(0.33, 30),
        new THREE.MeshStandardMaterial(PLASTIC)
      );
      bottom.rotation.x = -Math.PI / 2;
      bottom.position.y = -0.59;
      g.add(bottom);
      return g;
    }

    function makeLid() {
      const g = new THREE.Group();
      const lid = new THREE.Mesh(
        new THREE.CylinderGeometry(0.47, 0.45, 0.1, 30),
        new THREE.MeshStandardMaterial(SOLID)
      );
      g.add(lid);
      const dome = new THREE.Mesh(
        new THREE.SphereGeometry(0.2, 20, 12, 0, Math.PI * 2, 0, Math.PI / 2),
        new THREE.MeshStandardMaterial(SOLID)
      );
      dome.position.y = 0.05;
      g.add(dome);
      return g;
    }

    function makeStraw() {
      const g = new THREE.Group();
      const straw = new THREE.Mesh(
        new THREE.CylinderGeometry(0.05, 0.05, 1.0, 14),
        new THREE.MeshStandardMaterial(SOLID)
      );
      straw.rotation.z = 0.2;
      g.add(straw);
      return g;
    }

    const BUILDERS = { liquid: makeLiquid, body: makeBody, lid: makeLid, straw: makeStraw };

    const meshes = PARTS.map(function (p) {
      const g = BUILDERS[p.key]();
      g.position.set(p.home[0], p.home[1], p.home[2]);
      scene.add(g);
      return g;
    });

    /* ---- 拖拽旋转 ---- */

    let dragYaw = 0;
    let dragPitch = 0;
    let dragging = false;
    let lastX = 0;
    let lastY = 0;

    canvas.addEventListener('pointerdown', function (e) {
      dragging = true;
      lastX = e.clientX;
      lastY = e.clientY;
      if (canvas.setPointerCapture) canvas.setPointerCapture(e.pointerId);
    });
    canvas.addEventListener('pointermove', function (e) {
      if (!dragging) return;
      dragYaw += (e.clientX - lastX) * 0.005;
      dragPitch = Math.max(-0.35, Math.min(0.45, dragPitch + (e.clientY - lastY) * 0.003));
      lastX = e.clientX;
      lastY = e.clientY;
    });
    canvas.addEventListener('pointerup', function (e) {
      dragging = false;
      try { canvas.releasePointerCapture(e.pointerId); } catch (err) { /* 忽略 */ }
    });

    /* ---- 中文标签用 DOM 画，比贴图清楚 ---- */

    const projected = new THREE.Vector3();

    function projectToLayer(x, y, z) {
      projected.set(x, y, z).project(camera);
      // 投影到边缘时标签容易被面板裁掉，这里夹一下范围
      const marginX = 96;
      const marginY = 28;
      const px = (projected.x * 0.5 + 0.5) * box.clientWidth;
      const py = (-projected.y * 0.5 + 0.5) * box.clientHeight;
      return {
        x: Math.max(marginX, Math.min(box.clientWidth - marginX, px)),
        y: Math.max(marginY, Math.min(box.clientHeight - marginY, py)),
      };
    }

    const partLabels = PARTS.map(function (p) {
      const el = document.createElement('div');
      el.className = 'lb';
      el.innerHTML = '<b>' + p.name + '</b><i>→ ' + p.binName + '</i>';
      el.style.borderLeft = '3px solid ' + BIN_COLOR[p.bin];
      labelLayer.appendChild(el);
      return el;
    });

    const binLabels = bins.map(function (b) {
      const el = document.createElement('div');
      el.className = 'lb bin';
      el.textContent = b.name;
      labelLayer.appendChild(el);
      return el;
    });

    const mainLabel = document.createElement('div');
    mainLabel.className = 'lb main';
    mainLabel.innerHTML = '<b>未喝完的奶茶</b><i>复合垃圾 · 拆成 4 部分</i>';
    labelLayer.appendChild(mainLabel);

    /* ---- 主循环 ---- */

    function animate() {
      requestAnimationFrame(animate);

      const t = window.__screenNowT();
      const st = sample(t);

      // 相机轻微摆动，加用户拖拽
      const sway = Math.sin(t * 0.22) * 0.13;
      const cam = CAM_HOME.clone();
      cam.applyAxisAngle(new THREE.Vector3(0, 1, 0), sway + dragYaw);
      cam.y += dragPitch * 3.2;
      camera.position.lerp(cam, 0.08);
      camera.lookAt(CAM_LOOK);

      // 桶：呼吸 + 落桶脉冲
      bins.forEach(function (b) {
        const pulse = st.pulses[b.key] || 0;
        const k = 1 + pulse * 0.22;
        b.mouth.scale.set(k, k, 1);
        b.band.scale.set(k, k, 1);
        b.glow.material.opacity = 0.18 + pulse * 0.55;
        b.group.position.y = Math.sin(t * 0.9 + b.x) * 0.012;
      });

      // 部件：位置全部来自共享时间轴
      st.parts.forEach(function (s, i) {
        const g = meshes[i];
        const bob = Math.sin(t * 1.1 + i) * 0.035;
        const settled = s.phase === 'assembled' || s.phase === 'split' || s.phase === 'wait';
        g.position.set(s.pos[0], s.pos[1] + (settled ? bob : 0), s.pos[2]);
        g.scale.setScalar(s.scale);
        g.visible = s.visible;
        if (s.phase === 'assembled' || s.phase === 'split') g.rotation.y = t * 0.25;
        else if (s.phase === 'fly') g.rotation.y = 4.2 * ((t - flyWindow(i)[0]) / (flyWindow(i)[1] - flyWindow(i)[0]));
        else if (s.phase === 'reset') g.rotation.y = 4.2 * (1 - (t - T_RESET) / (T_RESET_END - T_RESET));
      });

      // 组装状态下只在杯子上方挂一个总标签
      mainLabel.style.opacity = st.assembled ? 1 : 0;
      if (st.assembled) {
        const s0 = projectToLayer(0, 3.95, 0);
        mainLabel.style.transform =
          'translate(-50%,-50%) translate(' + s0.x + 'px,' + s0.y + 'px)';
      }

      // 拆开之后，每个部件跟着自己的标签走
      st.parts.forEach(function (s, i) {
        const el = partLabels[i];
        const show = !st.assembled && s.visible && s.phase !== 'landed';
        el.style.opacity = show ? 1 : 0;
        if (show) {
          const q = projectToLayer(s.pos[0], s.pos[1] + 0.55, s.pos[2]);
          el.style.transform = 'translate(-50%,-50%) translate(' + q.x + 'px,' + q.y + 'px)';
        }
        partCards[i].classList.toggle('on', s.flying);
      });

      bins.forEach(function (b, i) {
        const el = binLabels[i];
        const q = projectToLayer(b.x, 0.28, b.z);
        el.style.transform = 'translate(-50%,-50%) translate(' + q.x + 'px,' + q.y + 'px)';
        el.classList.toggle('on', (st.pulses[b.key] || 0) > 0.2);
      });

      renderer.render(scene, camera);
    }

    function resizeGL() {
      const w = box.clientWidth;
      const h = box.clientHeight;
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    }

    resizeGL();
    animate();

    window.__screenRelayout3D = resizeGL;
    window.__scene3dOk = true;
  } catch (err) {
    window.__scene3dOk = false;
    window.__scene3dError = (err && err.message) ? err.message : String(err);
  }
})();
