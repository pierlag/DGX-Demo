import React, { useEffect, useRef, forwardRef, useImperativeHandle } from "react";
import { Engine } from "@babylonjs/core/Engines/engine";
import { Scene } from "@babylonjs/core/scene";
import { ArcRotateCamera } from "@babylonjs/core/Cameras/arcRotateCamera";
import { HemisphericLight } from "@babylonjs/core/Lights/hemisphericLight";
import { DirectionalLight } from "@babylonjs/core/Lights/directionalLight";
import { Vector3, Color3, Color4 } from "@babylonjs/core/Maths/math";
import { AppendSceneAsync } from "@babylonjs/core/Loading/sceneLoader";
import "@babylonjs/core/Helpers/sceneHelpers";
import "@babylonjs/loaders/glTF";

/**
 * BabylonJS viewer that loads a GLB model and lets the user orbit it with the
 * mouse (left-drag rotate, wheel zoom, right-drag pan).
 */
export default forwardRef(function Viewer3D({ src }, ref) {
  const canvasRef = useRef(null);
  const engineRef = useRef(null);
  const sceneRef = useRef(null);

  useImperativeHandle(ref, () => ({
    /** Render a fresh frame and return its centered square as a PNG data URL. */
    capture: () => {
      const engine = engineRef.current;
      const scene = sceneRef.current;
      const canvas = canvasRef.current;
      if (!engine || !scene || !canvas) return null;
      try {
        scene.render();
        const w = canvas.width;
        const h = canvas.height;
        const side = Math.min(w, h);
        const sx = (w - side) / 2;
        const sy = (h - side) / 2;
        const off = document.createElement("canvas");
        off.width = side;
        off.height = side;
        const ctx = off.getContext("2d");
        // Crop the centered square of the viewport (not the top of the frame).
        ctx.drawImage(canvas, sx, sy, side, side, 0, 0, side, side);
        return off.toDataURL("image/png");
      } catch {
        return null;
      }
    },
  }));

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const engine = new Engine(canvas, true, { preserveDrawingBuffer: true, stencil: true });
    engineRef.current = engine;

    const scene = new Scene(engine);
    sceneRef.current = scene;
    scene.clearColor = new Color4(0.04, 0.06, 0.09, 1);

    const camera = new ArcRotateCamera(
      "cam",
      Math.PI / 4,
      Math.PI / 3,
      4,
      Vector3.Zero(),
      scene
    );
    camera.attachControl(canvas, true);
    camera.wheelPrecision = 40;
    camera.lowerRadiusLimit = 0.5;
    camera.upperRadiusLimit = 50;
    camera.minZ = 0.01;

    const hemi = new HemisphericLight("hemi", new Vector3(0, 1, 0), scene);
    hemi.intensity = 0.9;
    const dir = new DirectionalLight("dir", new Vector3(-1, -2, -1), scene);
    dir.intensity = 1.1;

    let disposed = false;
    if (src) {
      AppendSceneAsync(src, scene)
        .then(() => {
          if (disposed) return;
          // Auto-frame the camera on the imported model bounds.
          const meshes = scene.meshes.filter((m) => m.getTotalVertices && m.getTotalVertices() > 0);
          if (meshes.length) {
            let min = null;
            let max = null;
            meshes.forEach((m) => {
              m.computeWorldMatrix(true);
              const bb = m.getBoundingInfo().boundingBox;
              const lo = bb.minimumWorld;
              const hi = bb.maximumWorld;
              min = min ? Vector3.Minimize(min, lo) : lo.clone();
              max = max ? Vector3.Maximize(max, hi) : hi.clone();
            });
            const center = min.add(max).scale(0.5);
            const size = max.subtract(min).length();
            camera.setTarget(center);
            camera.radius = Math.max(size * 1.4, 0.5);
            camera.lowerRadiusLimit = size * 0.2;
            camera.upperRadiusLimit = size * 8;
          }
        })
        .catch((e) => console.error("Babylon load error", e));
    }

    engine.runRenderLoop(() => scene.render());
    const onResize = () => engine.resize();
    window.addEventListener("resize", onResize);

    return () => {
      disposed = true;
      window.removeEventListener("resize", onResize);
      scene.dispose();
      engine.dispose();
      engineRef.current = null;
      sceneRef.current = null;
    };
  }, [src]);

  return (
    <canvas
      ref={canvasRef}
      className="h-full w-full rounded-xl outline-none"
      style={{ touchAction: "none" }}
    />
  );
});
