import os
import sys
import json
import time
import subprocess
import urllib.request
import asyncio
import base64
from pathlib import Path
import websockets

EDGE_EXE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9226

async def test_and_screenshot():
    user_data_dir = Path(os.environ["TEMP"]) / f"edge_test_profile_{int(time.time())}"
    cmd = [
        EDGE_EXE,
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--headless=new",
        "--window-size=1600,950",
        "about:blank"
    ]
    proc = subprocess.Popen(cmd)
    try:
        await asyncio.sleep(1.5)
        res = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json")
        targets = json.loads(res.read().decode())
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
                    r = json.loads(await ws.recv())
                    if r.get("id") == msg_id:
                        return r

            await send_cmd("Runtime.enable")
            await send_cmd("Page.enable")

            # 1. Test W1.0
            w_path = Path("Aircraft Design Tool W1.0.html").resolve().as_uri()
            print("Navigating to W1.0:", w_path)
            await send_cmd("Page.navigate", {"url": w_path})
            await asyncio.sleep(2.0)

            # Add loop cuts to main-wing
            res = await send_cmd("Runtime.evaluate", {
                "expression": """
                (() => {
                    const parts = getAllActiveParts();
                    const target = parts.find(c => c.sections && c.sections.length > 0) || parts[0];
                    handleSelectComponent(target.id);
                    performLoopCut(target.id, 3, 0);
                    refresh();
                    

                    const shape = document.querySelector('#components-layer g.interactive-shape');
                    const path = shape ? shape.querySelector('path') : null;
                    const d = path ? path.getAttribute('d') : '';
                    const mCount = (d.match(/M/g) || []).length;
                    const lCount = (d.match(/L/g) || []).length;
                    const polygons = document.querySelectorAll('#components-layer polygon');
                    const polyStrokes = Array.from(polygons).map(p => p.getAttribute('stroke'));
                    
                    return {
                        targetId: target.id,
                        sectionsCount: target.sections ? target.sections.length : 0,
                        d,
                        mCount,
                        lCount,
                        polyStrokes
                    };
                })()
                """,
                "returnByValue": True
            })
            if "exceptionDetails" in res.get("result", {}):
                print("JS ERROR in W1.0:", res["result"]["exceptionDetails"])
            val = res["result"]["result"].get("value", {})
            print("W1.0 Outline Check:")
            print("  Target:", val.get("targetId"))
            print("  Sections:", val.get("sectionsCount"))
            print("  Outer edge count (M):", val.get("mCount"))
            print("  Path d:", val.get("d"))

            # Capture screenshot of W1.0
            shot_res = await send_cmd("Page.captureScreenshot", {"format": "png"})
            img_data = base64.b64decode(shot_res["result"]["data"])
            shot_path = Path("C:/Users/Victor/.gemini/antigravity/brain/aeb4bcd8-b84f-461d-a02c-750035953491/w1_0_aero_loopcut.png")
            shot_path.write_bytes(img_data)
            print(f"Saved screenshot to {shot_path}")

            # 2. Test S01.9
            s_path = Path("Aircraft Design Tool S01.9.html").resolve().as_uri()
            print("\nNavigating to S01.9:", s_path)
            await send_cmd("Page.navigate", {"url": s_path})
            await asyncio.sleep(2.0)

            res_s = await send_cmd("Runtime.evaluate", {
                "expression": """
                (() => {
                    const parts = getAllActiveParts();
                    const target = parts.find(c => c.sections && c.sections.length > 0) || parts[0];
                    handleSelectComponent(target.id);
                    performLoopCut(target.id, 3, 0);
                    refresh();
                    
                    const shape = document.querySelector('#components-layer g.interactive-shape');
                    const path = shape ? shape.querySelector('path') : null;
                    const d = path ? path.getAttribute('d') : '';
                    const mCount = (d.match(/M/g) || []).length;
                    const lCount = (d.match(/L/g) || []).length;
                    const polygons = document.querySelectorAll('#components-layer polygon');
                    const polyStrokes = Array.from(polygons).map(p => p.getAttribute('stroke'));
                    
                    return {
                        targetId: target.id,
                        sectionsCount: target.sections ? target.sections.length : 0,
                        d,
                        mCount,
                        lCount,
                        polyStrokes
                    };
                })()
                """,
                "returnByValue": True
            })
            val_s = res_s["result"]["result"].get("value", {})
            print("S01.9 Outline Check:")
            print("  Target:", val_s.get("targetId"))
            print("  Sections:", val_s.get("sectionsCount"))
            print("  Outer edge count (M):", val_s.get("mCount"))
            print("  Path d:", val_s.get("d"))

            shot_res_s = await send_cmd("Page.captureScreenshot", {"format": "png"})
            img_data_s = base64.b64decode(shot_res_s["result"]["data"])
            shot_path_s = Path("C:/Users/Victor/.gemini/antigravity/brain/aeb4bcd8-b84f-461d-a02c-750035953491/s01_9_loopcut.png")
            shot_path_s.write_bytes(img_data_s)
            print(f"Saved screenshot to {shot_path_s}")

            assert val["mCount"] == 4, f"W1.0 expected 4 outline boundary edges, got {val['mCount']}"
            assert val_s["mCount"] == 4, f"S01.9 expected 4 outline boundary edges, got {val_s['mCount']}"
            assert all(s == "none" for s in val["polyStrokes"]), "W1.0 facet polygons must have stroke='none'"
            assert all(s == "none" for s in val_s["polyStrokes"]), "S01.9 facet polygons must have stroke='none'"
            print("\n===> ALL CHECKS PASSED: NO INTERNAL LOOP CUT LINES IN W1.0 OR S01.9! <===")

    finally:
        proc.terminate()
        proc.wait()

if __name__ == "__main__":
    asyncio.run(test_and_screenshot())
