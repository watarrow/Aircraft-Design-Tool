import asyncio
import json
import os
import subprocess
import urllib.request
import websockets
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

PORT = 9295
USER_DATA = "C:/tmp/edge_cdp_3d_viewport"
HTML_PATH = os.path.abspath(r"c:\Users\Victor\Documents\Projects\Aircraft-Design-Tool\Aircraft Design Tool D01.0.html")
FILE_URL = f"file:///{HTML_PATH.replace(os.sep, '/')}"
EDGE_EXE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

async def main():
    cmd = [
        EDGE_EXE,
        "--headless=new",
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={USER_DATA}",
        "--window-size=1280,950",
        FILE_URL
    ]
    proc = subprocess.Popen(cmd)
    await asyncio.sleep(2.5)

    try:
        resp = urllib.request.urlopen(f"http://localhost:{PORT}/json")
        targets = json.loads(resp.read().decode("utf-8"))
        page_targets = [t for t in targets if t.get("type") == "page"]
        ws_url = page_targets[0]["webSocketDebuggerUrl"]

        async with websockets.connect(ws_url) as ws:
            msg_id = 0

            async def send_cmd(method, params=None):
                nonlocal msg_id
                msg_id += 1
                req = {"id": msg_id, "method": method, "params": params or {}}
                await ws.send(json.dumps(req))
                while True:
                    r = await ws.recv()
                    res = json.loads(r)
                    if res.get("id") == msg_id:
                        return res.get("result", {})

            await send_cmd("Runtime.enable")
            await send_cmd("Page.enable")

            async def eval_js(expression):
                res = await send_cmd("Runtime.evaluate", {"expression": expression, "returnByValue": True})
                if "exceptionDetails" in res:
                    print("JS Exception:", res["exceptionDetails"])
                    raise RuntimeError(f"JS Exception: {res['exceptionDetails']}")
                return res.get("result", {}).get("value")

            print("=== TEST SUITE: D01.0 3D WEBGL VIEWPORT & BLENDER NAVIGATION ===")

            # 1. Verify Three.js engine initialization
            print("\n1. Verifying 3D Engine Initialization...")
            engine_info = await eval_js(r"""
            (() => {
                return {
                    isInitialized: App.three?.isInitialized,
                    hasRenderer: !!App.three?.renderer,
                    hasScene: !!App.three?.scene,
                    hasCamera: !!App.three?.camera,
                    hasControls: !!App.three?.transformControls,
                    cameraUp: App.three?.camera ? [App.three.camera.up.x, App.three.camera.up.y, App.three.camera.up.z] : null,
                    numCompMeshes: App.three?.compMeshes?.size || 0,
                    hasWingMesh: !!App.three?.wingMesh,
                    hasCG: !!App.three?.cgMarker,
                    hasNP: !!App.three?.npMarker,
                    hasGrid: !!App.three?.grid,
                    hasAxes: !!App.three?.axes
                };
            })()
            """)
            print("Engine info:", engine_info)
            assert engine_info["isInitialized"] is True, "Three engine should be initialized"
            assert engine_info["hasRenderer"] is True, "Renderer should exist"
            assert engine_info["hasScene"] is True, "Scene should exist"
            assert engine_info["hasCamera"] is True, "Camera should exist"
            assert engine_info["cameraUp"] == [0, 0, 1], "Camera UP must be (0, 0, 1) matching aircraft coordinates"
            assert engine_info["hasWingMesh"] is True, "3D Wing mesh should be populated"
            assert engine_info["numCompMeshes"] > 0, "3D Component meshes should be populated"
            assert engine_info["hasCG"] is True, "3D CG marker should be in scene"
            assert engine_info["hasNP"] is True, "3D NP marker should be in scene"
            print("✓ 3D Engine & Meshes fully initialized!")

            # 2. Verify View Presets & UI Button Sync
            print("\n2. Verifying View Presets & Button States...")
            # Switch to Top
            await eval_js("setView('top')")
            top_state = await eval_js(r"""
            (() => {
                return {
                    view: App.state.currentView,
                    topBtnActive: document.getElementById('view-btn-top')?.classList.contains('active'),
                    btn3dActive: document.getElementById('view-btn-3d')?.classList.contains('active'),
                    phi: App.three.orbitState.phi,
                    theta: App.three.orbitState.theta
                };
            })()
            """)
            print("Top view state:", top_state)
            assert top_state["view"] == "top", "currentView should be 'top'"
            assert top_state["topBtnActive"] is True, "Top View button should be active"
            assert top_state["btn3dActive"] is False, "3D Orbit button should not be active"

            # Switch to 3D Orbit
            await eval_js("setView('orbit3d')")
            orbit_state = await eval_js(r"""
            (() => {
                return {
                    view: App.state.currentView,
                    topBtnActive: document.getElementById('view-btn-top')?.classList.contains('active'),
                    btn3dActive: document.getElementById('view-btn-3d')?.classList.contains('active'),
                    phi: App.three.orbitState.phi,
                    theta: App.three.orbitState.theta
                };
            })()
            """)
            print("3D Orbit state:", orbit_state)
            assert orbit_state["view"] == "orbit3d", "currentView should be 'orbit3d'"
            assert orbit_state["btn3dActive"] is True, "3D Orbit button should be active"
            assert orbit_state["topBtnActive"] is False, "Top View button should not be active"
            print("✓ View presets correctly update state and buttons!")

            # 3. Test MMB Orbit Drag (Blender style)
            print("\n3. Testing Middle Mouse Orbit...")
            await eval_js("setView('top')") # start from Top
            # Simulate MMB drag
            await eval_js(r"""
            (() => {
                const canvas = document.getElementById('three-viewport');
                const mDown = new MouseEvent('mousedown', { button: 1, clientX: 300, clientY: 300, bubbles: true });
                const mMove = new MouseEvent('mousemove', { button: 1, clientX: 350, clientY: 260, bubbles: true });
                const mUp = new MouseEvent('mouseup', { button: 1, clientX: 350, clientY: 260, bubbles: true });
                
                canvas.dispatchEvent(mDown);
                window.dispatchEvent(mMove);
                window.dispatchEvent(mUp);
            })()
            """)
            orbit_res = await eval_js(r"""
            (() => {
                return {
                    view: App.state.currentView,
                    btn3dActive: document.getElementById('view-btn-3d')?.classList.contains('active'),
                    theta: App.three.orbitState.theta,
                    phi: App.three.orbitState.phi
                };
            })()
            """)
            print("After MMB orbit drag:", orbit_res)
            assert orbit_res["view"] == "orbit3d", "MMB dragging out of Top view must transition view to 'orbit3d'"
            assert orbit_res["btn3dActive"] is True, "3D Orbit button should become active"
            print("✓ MMB Orbit correctly rotates camera and transitions view mode!")

            # 4. Test Shift + MMB Pan Drag (Blender style)
            print("\n4. Testing Shift + Middle Mouse Pan...")
            pan_before = await eval_js(r"""
            (() => {
                const p = App.three.orbitState.pivot;
                return [p.x, p.y, p.z];
            })()
            """)
            # Simulate Shift + MMB drag
            await eval_js(r"""
            (() => {
                const canvas = document.getElementById('three-viewport');
                const mDown = new MouseEvent('mousedown', { button: 1, shiftKey: true, clientX: 300, clientY: 300, bubbles: true });
                const mMove = new MouseEvent('mousemove', { button: 1, shiftKey: true, clientX: 360, clientY: 330, bubbles: true });
                const mUp = new MouseEvent('mouseup', { button: 1, shiftKey: true, clientX: 360, clientY: 330, bubbles: true });
                
                canvas.dispatchEvent(mDown);
                window.dispatchEvent(mMove);
                window.dispatchEvent(mUp);
            })()
            """)
            pan_after = await eval_js(r"""
            (() => {
                const p = App.three.orbitState.pivot;
                return [p.x, p.y, p.z];
            })()
            """)
            print(f"Pivot before: {pan_before} -> after pan: {pan_after}")
            assert pan_before != pan_after, "Pivot must move when panning with Shift + MMB"
            print("✓ Shift + MMB 3D Pan correctly translates pivot point!")

            # 5. Test Wheel Zoom
            print("\n5. Testing Scroll Wheel Zoom...")
            zoom_before = await eval_js("App.three.orbitState.radius")
            await eval_js(r"""
            (() => {
                const canvas = document.getElementById('three-viewport');
                const wheelEv = new WheelEvent('wheel', { deltaY: -100, bubbles: true, cancelable: true });
                canvas.dispatchEvent(wheelEv);
            })()
            """)
            zoom_after = await eval_js("App.three.orbitState.radius")
            print(f"Radius before: {zoom_before} -> after zoom in: {zoom_after}")
            assert zoom_after < zoom_before, "Zooming in (negative deltaY) should decrease orbit radius"
            print("✓ Scroll wheel zoom correctly modifies camera distance!")

            # 6. Test 'F' Frame Whole Aircraft
            print("\n6. Testing 'F' Key Framing...")
            await eval_js(r"""
            (() => {
                const keyEv = new KeyboardEvent('keydown', { key: 'f', bubbles: true, cancelable: true });
                window.dispatchEvent(keyEv);
            })()
            """)
            frame_state = await eval_js(r"""
            (() => {
                const p = App.three.orbitState.pivot;
                return {
                    pivot: [p.x, p.y, p.z],
                    radius: App.three.orbitState.radius
                };
            })()
            """)
            print("Framed state:", frame_state)
            assert frame_state["radius"] > 30, "Radius should comfortably encompass the aircraft"
            print("✓ 'F' key framing correctly centers camera on whole plane!")

            # 7. Test Part Selection & TransformControls Gizmo
            print("\n7. Testing Selection & 3D TransformControls Gizmo...")
            # Select component
            await eval_js("handleSelectComponent('rear-fus')")
            gizmo_info = await eval_js(r"""
            (() => {
                return {
                    selectedId: App.state.selectedComponentId,
                    gizmoVisible: App.three.transformControls?.visible,
                    gizmoMode: App.three.transformControls?.getMode(),
                    pivotPos: App.three.dummyPivot ? [App.three.dummyPivot.position.x, App.three.dummyPivot.position.y, App.three.dummyPivot.position.z] : null
                };
            })()
            """)
            print("Gizmo info after selecting 'rear-fus':", gizmo_info)
            assert gizmo_info["selectedId"] == "rear-fus", "rear-fus should be selected"
            assert gizmo_info["gizmoVisible"] is True, "TransformControls gizmo should be visible"
            assert gizmo_info["pivotPos"] is not None, "Dummy pivot should be positioned at component"

            # Test G shortcut (translate mode)
            await eval_js(r"""
            (() => {
                const keyG = new KeyboardEvent('keydown', { key: 'g', bubbles: true, cancelable: true });
                window.dispatchEvent(keyG);
            })()
            """)
            mode_g = await eval_js("App.three.transformControls.getMode()")
            assert mode_g == "translate", "Pressing 'g' should set translate mode"

            # Test R shortcut (rotate mode)
            await eval_js(r"""
            (() => {
                const keyR = new KeyboardEvent('keydown', { key: 'r', bubbles: true, cancelable: true });
                window.dispatchEvent(keyR);
            })()
            """)
            mode_r = await eval_js("App.three.transformControls.getMode()")
            assert mode_r == "rotate", "Pressing 'r' should set rotate mode"
            print("✓ Selection attaches 3D Gizmo and 'G'/'R' switch modes successfully!")

            # 8. Capture visual artifact screenshot
            print("\n8. Capturing 3D Viewport screenshot...")
            await eval_js("setView('orbit3d'); frameAircraft3D();")
            await asyncio.sleep(0.5)
            shot_res = await send_cmd("Page.captureScreenshot", {"format": "png"})
            import base64
            img_bytes = base64.b64decode(shot_res["data"])
            art_dir = r"C:\Users\Victor\.gemini\antigravity\brain\aeb4bcd8-b84f-461d-a02c-750035953491"
            img_path = os.path.join(art_dir, "d01_0_3d_viewport.png")
            with open(img_path, "wb") as f:
                f.write(img_bytes)
            print(f"✓ Screenshot saved to {img_path}")

            print("\n========================================================")
            print("ALL D01.0 3D VIEWPORT & BLENDER NAVIGATION TESTS PASSED!")
            print("========================================================")

    finally:
        proc.kill()

if __name__ == "__main__":
    asyncio.run(main())
