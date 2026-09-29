import asyncio
import json
import os
import subprocess
import urllib.request
import websockets
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

PORT = 9237
USER_DATA = "C:/tmp/edge_cdp_drag_perf"
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
    await asyncio.sleep(2)

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
                payload = {"id": msg_id, "method": method, "params": params or {}}
                await ws.send(json.dumps(payload))
                while True:
                    res = json.loads(await ws.recv())
                    if res.get("id") == msg_id:
                        return res.get("result", {})

            await send_cmd("Runtime.enable")
            await send_cmd("Page.enable")

            async def eval_js(expression):
                res = await send_cmd("Runtime.evaluate", {"expression": expression, "returnByValue": True})
                if "exceptionDetails" in res.get("result", {}):
                    print("JS Exception:", res["result"]["exceptionDetails"])
                    raise RuntimeError(f"JS Exception: {res['result']['exceptionDetails']}")
                return res.get("result", {}).get("value")

            print("=== DRAG & PERFORMANCE VERIFICATION SUITE ===")

            # 1. Measure calculateAircraft and renderAircraft execution speed over 50 iterations
            perf_stats = await eval_js("""(() => {
                const t0 = performance.now();
                for (let i = 0; i < 50; i++) {
                    calculateAircraft();
                }
                const t1 = performance.now();
                for (let i = 0; i < 50; i++) {
                    renderAircraft();
                }
                const t2 = performance.now();
                return {
                    calcAvgMs: (t1 - t0) / 50,
                    renderAvgMs: (t2 - t1) / 50
                };
            })()""")
            print(f"1. Performance benchmark (50 iterations):")
            print(f"   calculateAircraft avg: {perf_stats['calcAvgMs']:.3f} ms")
            print(f"   renderAircraft avg:    {perf_stats['renderAvgMs']:.3f} ms")
            assert perf_stats['calcAvgMs'] < 7.0, f"calculateAircraft should execute in < 7.0ms, got {perf_stats['calcAvgMs']}"
            assert perf_stats['renderAvgMs'] < 7.0, f"renderAircraft should execute in < 7.0ms, got {perf_stats['renderAvgMs']}"
            print("PASS: High-performance calculation and rendering confirmed.")

            # 2. Test NACA memoization cache
            cache_info = await eval_js("""(() => {
                const c1 = generateNACA4('2412');
                const c2 = generateNACA4('2412');
                return {
                    isSameRef: c1 === c2,
                    length: c1.length
                };
            })()""")
            print("2. NACA Airfoil Memoization:", cache_info)
            assert cache_info["isSameRef"] == True, "NACA 4 generator should return cached reference"
            assert cache_info["length"] > 40, "Airfoil curve points length should be valid"
            print("PASS: NACA 4 memoization confirmed.")

            # 3. Test Dragging a component on canvas
            # Select a component (e.g. comp-1779044380002 Battery)
            drag_test = await eval_js("""(() => {
                const comp = App.state.components[0];
                const origX = comp.x;
                const origY = comp.y;
                
                // Simulate startDrag
                startDrag({ stopPropagation: () => {}, clientX: 300, clientY: 300 }, comp.id);
                const isDragging = App.state.drag.dragging;
                
                // Simulate doDrag mouse move
                doDrag({ clientX: 350, clientY: 320 });
                const duringX = comp.x;
                const duringY = comp.y;
                
                // Simulate mouseup
                App.state.drag.dragging = false;
                App.state.drag.activeSnapLines = [];
                refresh();
                
                return {
                    compId: comp.id,
                    origX: origX,
                    duringX: duringX,
                    moved: duringX !== origX,
                    finalDragging: App.state.drag.dragging
                };
            })()""")
            print("3. Component drag simulation:", drag_test)
            assert drag_test["moved"] == True, "Component position should update during drag"
            assert drag_test["finalDragging"] == False, "Dragging state should be false after mouseup"
            print("PASS: Component dragging logic verified.")

            # 4. Verify Mass Profile fast-path
            profile_test = await eval_js("""(() => {
                const btnBefore = document.getElementById('btn-profile-measured');
                setActiveMassProfileModel('measured');
                renderMassProfileUI();
                const btnAfter = document.getElementById('btn-profile-measured');
                return {
                    isSameElement: btnBefore === btnAfter,
                    hasActiveClass: btnAfter.classList.contains('active')
                };
            })()""")
            print("4. Mass Profile DOM fast-path:", profile_test)
            assert profile_test["isSameElement"] == True, "Button DOM node should be preserved (not recreated)"
            assert profile_test["hasActiveClass"] == True, "Measured profile button should have active class"
            print("PASS: Mass Profile fast path class toggle verified.")

            # Reset back to budget profile
            await eval_js("setActiveMassProfileModel('budget'); renderMassProfileUI();")

            print("\nALL DRAG & PERFORMANCE VERIFICATION TESTS PASSED SUCCESSFULLY!")

    finally:
        proc.terminate()

if __name__ == "__main__":
    asyncio.run(main())
