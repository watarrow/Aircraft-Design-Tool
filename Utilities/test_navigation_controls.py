import asyncio
import json
import os
import subprocess
import urllib.request
import websockets
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

PORT = 9292
USER_DATA = "C:/tmp/edge_cdp_navigation_controls"
HTML_PATH = os.path.abspath(r"c:\Users\Victor\Documents\Projects\Aircraft-Design-Tool\Aircraft Design Tool S01.8.html")
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

            print("=== TEST SUITE: UNIVERSAL NAVIGATION CONTROLS (MMB PAN, SCROLL ZOOM, F RESET) ===")

            # 1. Baseline viewbox (whole plane)
            print("\n1. Verifying initial whole-plane view...")
            init_state = await eval_js(r"""
            (() => {
                const svg = document.getElementById('visualizer');
                const vb = svg.getAttribute('viewBox').split(/\s+/).map(Number);
                return {
                    view: App.state.currentView,
                    viewBox: vb
                };
            })()
            """)
            print("   Initial state:", init_state)
            assert init_state["view"] == "top"
            assert len(init_state["viewBox"]) == 4
            orig_vb = init_state["viewBox"]
            print(f"   PASS: Whole plane viewBox is initialized: {orig_vb}")

            # 2. Middle mouse + drag to pan
            print("\n2. Testing Middle Mouse + Drag to Pan...")
            pan_res = await eval_js(r"""
            (() => {
                const svg = document.getElementById('visualizer');
                const rect = svg.getBoundingClientRect();
                const startX = rect.left + rect.width / 2;
                const startY = rect.top + rect.height / 2;

                // 1. Middle mouse down (button 1)
                const downEvt = new MouseEvent('mousedown', {
                    bubbles: true,
                    cancelable: true,
                    clientX: startX,
                    clientY: startY,
                    button: 1,
                    buttons: 4
                });
                svg.dispatchEvent(downEvt);

                const isPanningStarted = !!(App.ui.camera && App.ui.camera.isPanning);

                // 2. Drag by 100px right, 50px down
                const moveEvt = new MouseEvent('mousemove', {
                    bubbles: true,
                    cancelable: true,
                    clientX: startX + 100,
                    clientY: startY + 50,
                    button: 1,
                    buttons: 4
                });
                window.dispatchEvent(moveEvt);

                const pannedVB = svg.getAttribute('viewBox').split(/\s+/).map(Number);

                // 3. Middle mouse up
                const upEvt = new MouseEvent('mouseup', {
                    bubbles: true,
                    cancelable: true,
                    clientX: startX + 100,
                    clientY: startY + 50,
                    button: 1,
                    buttons: 0
                });
                window.dispatchEvent(upEvt);

                const isPanningEnded = !(App.ui.camera && App.ui.camera.isPanning);

                return {
                    isPanningStarted,
                    isPanningEnded,
                    pannedVB,
                    savedCam: App.ui.camera?.views?.top
                };
            })()
            """)
            print("   Pan result:", pan_res)
            assert pan_res["isPanningStarted"], "Middle click should initiate camera panning"
            assert pan_res["isPanningEnded"], "Middle release should end camera panning"
            # Moving mouse right should shift viewBox origin left (pannedVB[0] < orig_vb[0])
            assert pan_res["pannedVB"][0] < orig_vb[0], f"ViewBox X should have decreased, got {pan_res['pannedVB'][0]} vs {orig_vb[0]}"
            # Moving mouse down should shift viewBox origin up (pannedVB[1] < orig_vb[1])
            assert pan_res["pannedVB"][1] < orig_vb[1], f"ViewBox Y should have decreased, got {pan_res['pannedVB'][1]} vs {orig_vb[1]}"
            print("   PASS: Middle mouse drag successfully pans the view.")

            # 3. Scroll wheel zooms into cursor position
            print("\n3. Testing Scroll Wheel Zoom to Cursor Position...")
            zoom_res = await eval_js(r"""
            (() => {
                const svg = document.getElementById('visualizer');
                const rect = svg.getBoundingClientRect();
                
                // Pick an off-center cursor position: 70% X, 30% Y
                const cursorClientX = rect.left + rect.width * 0.7;
                const cursorClientY = rect.top + rect.height * 0.3;

                // Point in SVG space under cursor BEFORE zoom
                const ptBefore = getSVGPoint(svg, cursorClientX, cursorClientY);
                const vbBefore = svg.getAttribute('viewBox').split(/\s+/).map(Number);

                // Wheel scroll to zoom in (negative deltaY)
                const wheelEvt = new WheelEvent('wheel', {
                    bubbles: true,
                    cancelable: true,
                    clientX: cursorClientX,
                    clientY: cursorClientY,
                    deltaY: -120
                });
                svg.dispatchEvent(wheelEvt);

                const vbAfter = svg.getAttribute('viewBox').split(/\s+/).map(Number);
                // Point in SVG space under the same cursor AFTER zoom
                const ptAfter = getSVGPoint(svg, cursorClientX, cursorClientY);

                return {
                    vbBefore,
                    vbAfter,
                    widthBefore: vbBefore[2],
                    widthAfter: vbAfter[2],
                    ptBefore: { x: ptBefore.x, y: ptBefore.y },
                    ptAfter: { x: ptAfter.x, y: ptAfter.y },
                    distDiff: Math.hypot(ptAfter.x - ptBefore.x, ptAfter.y - ptBefore.y)
                };
            })()
            """)
            print("   Zoom in result:", zoom_res)
            assert zoom_res["widthAfter"] < zoom_res["widthBefore"], "Zoom in should decrease viewBox width"
            # Invariant: the point under the cursor should remain identical (distDiff < 0.05 SVG units, sub-pixel accuracy)
            assert zoom_res["distDiff"] < 0.05, f"Point under cursor should be invariant, diff={zoom_res['distDiff']}"
            print(f"   PASS: Scroll wheel zooms directly into cursor position with sub-pixel precision (diff={zoom_res['distDiff']:.4f}).")

            # 4. F key resets the view to see the whole plane
            print("\n4. Testing F key resets view to see whole plane...")
            f_reset_res = await eval_js(r"""
            (() => {
                const svg = document.getElementById('visualizer');
                
                // Press F
                const fEvt = new KeyboardEvent('keydown', {
                    bubbles: true,
                    cancelable: true,
                    key: 'f',
                    code: 'KeyF'
                });
                window.dispatchEvent(fEvt);

                const vbReset = svg.getAttribute('viewBox').split(/\s+/).map(Number);
                const legendEl = document.getElementById('shortcuts-legend') || document.getElementById('legend');
                const legendHtml = legendEl?.innerHTML || '';

                return {
                    vbReset,
                    cameraViewTop: App.ui.camera?.views?.top,
                    hasLegendResetText: legendHtml.includes('Reset View (Whole Plane)') || legendHtml.includes('Reset View')
                };
            })()
            """)
            print("   F Reset result:", f_reset_res)
            assert f_reset_res["cameraViewTop"] is None, "F key should reset custom camera for current view to null"
            # Viewbox after F reset should match the original whole-plane viewBox
            for i in range(4):
                assert abs(f_reset_res["vbReset"][i] - orig_vb[i]) < 0.01, f"ViewBox index {i} mismatch after F reset: {f_reset_res['vbReset'][i]} vs {orig_vb[i]}"
            assert f_reset_res["hasLegendResetText"], "Shortcuts legend should describe F as Reset View"
            print("   PASS: F key perfectly resets the view to frame the whole plane.")

            # 5. Selection and left-click interaction
            print("\n5. Verifying component selection and left-click drag...")
            select_res = await eval_js("""
            (() => {
                handleSelectComponent('vert-stab');
                const isSelected = App.state.selectedComponentId === 'vert-stab';

                // Middle click on component should NOT trigger component drag
                const svg = document.getElementById('visualizer');
                const midDownOnComp = new MouseEvent('mousedown', {
                    bubbles: true,
                    clientX: 200,
                    clientY: 200,
                    button: 1
                });
                startDrag(midDownOnComp, 'vert-stab');
                const dragNotTriggered = !App.state.drag.dragging;

                return {
                    isSelected,
                    dragNotTriggered
                };
            })()
            """)
            print("   Selection and drag check:", select_res)
            assert select_res["isSelected"], "Component selection should work normally"
            assert select_res["dragNotTriggered"], "Middle click should NOT trigger component drag"
            print("   PASS: Component selection works cleanly and middle click does not drag parts.")

            print("\n=== ALL UNIVERSAL NAVIGATION CONTROLS TESTS PASSED! ===")

    finally:
        proc.terminate()

if __name__ == "__main__":
    asyncio.run(main())
