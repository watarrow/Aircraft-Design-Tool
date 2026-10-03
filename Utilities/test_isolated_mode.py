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
PORT = 9227

async def test_file_isolate(ws, html_path, label, screenshot_prefix):
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

    async def eval_js(expr):
        res = await send_cmd("Runtime.evaluate", {
            "expression": expr,
            "returnByValue": True,
            "awaitPromise": True
        })
        if "exceptionDetails" in res.get("result", {}):
            print(f"[{label}] JS EXCEPTION:", res["result"]["exceptionDetails"])
        return res["result"]["result"].get("value")

    print(f"\n--- Testing {label}: {html_path} ---")
    await send_cmd("Page.navigate", {"url": html_path})
    await asyncio.sleep(2.0)

    # 1. Select horiz-stab and press 'i' to isolate
    init_state = await eval_js("""
    (async () => {
        handleSelectComponent('horiz-stab');
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'i', code: 'KeyI', bubbles: true }));
        await new Promise(r => setTimeout(r, 60));
        
        const isIsolated = App.ui.viewParams.isIsolated;
        const inSet = App.ui.viewParams.isolatedSet.has('horiz-stab');
        
        // Find horiz-stab group
        const horizGroup = document.querySelector('#components-layer g.interactive-shape');
        
        // Check other parts transparency
        // Wing
        const wingPoly = document.querySelector('#wing-layer path, #wing-layer polygon');
        const wingOpacity = wingPoly ? (wingPoly.style.opacity || wingPoly.getAttribute('opacity') || '1') : 'none';
        
        // Outliner eye icons
        const horizItem = document.querySelector('#comp-list .outliner-item[data-id="horiz-stab"]');
        const horizEye = horizItem ? horizItem.querySelector('.outliner-icon') : null;
        const horizEyeOpacity = horizEye ? horizEye.style.opacity : 'none';
        
        const vertItem = document.querySelector('#comp-list .outliner-item[data-id="vert-stab"]');
        const vertEye = vertItem ? vertItem.querySelector('.outliner-icon') : null;
        const vertEyeOpacity = vertEye ? vertEye.style.opacity : 'none';
        
        // Find vert-stab group in canvas
        // Search through interactive-shape groups
        const groups = Array.from(document.querySelectorAll('#components-layer g.interactive-shape'));
        const opacities = groups.map(g => g.style.opacity || '1');
        
        return {
            isIsolated,
            inSet,
            wingOpacity,
            horizEyeOpacity,
            vertEyeOpacity,
            opacities,
            numGhosted: opacities.filter(o => o === '0.15').length,
            numFull: opacities.filter(o => o !== '0.15').length
        };
    })()
    """)

    print(f"[{label}] After pressing 'I' on horiz-stab:")
    print(f"  isIsolated: {init_state['isIsolated']}, inSet: {init_state['inSet']}")
    print(f"  Wing opacity: {init_state['wingOpacity']} (expected '0.15')")
    print(f"  Horiz-stab eye icon opacity: {init_state['horizEyeOpacity']} (expected '1')")
    print(f"  Vert-stab eye icon opacity: {init_state['vertEyeOpacity']} (expected '0.2')")
    print(f"  Canvas components: {init_state['numFull']} full, {init_state['numGhosted']} ghosted (0.15 opacity)")
    
    assert init_state['isIsolated'] is True, "Must be in isolated mode"
    assert init_state['inSet'] is True, "horiz-stab must be in isolatedSet"
    assert init_state['wingOpacity'] == '0.15', f"Wing must have increased transparency (0.15), got {init_state['wingOpacity']}"
    assert init_state['horizEyeOpacity'] == '1', f"horiz-stab eye icon must be 1, got {init_state['horizEyeOpacity']}"
    assert init_state['vertEyeOpacity'] == '0.2', f"vert-stab eye icon must be 0.2, got {init_state['vertEyeOpacity']}"
    assert init_state['numGhosted'] > 0, "Other components must have 0.15 opacity"

    # Screenshot 1: Isolated horiz-stab with transparent other parts
    shot1 = await send_cmd("Page.captureScreenshot", {"format": "png"})
    Path(f"C:/Users/Victor/.gemini/antigravity/brain/aeb4bcd8-b84f-461d-a02c-750035953491/{screenshot_prefix}_isolated.png").write_bytes(base64.b64decode(shot1["result"]["data"]))

    # 2. Click the eye icon of vert-stab in the parts tree on the left
    click_eye_state = await eval_js("""
    (async () => {
        const vertItem = document.querySelector('#comp-list .outliner-item[data-id="vert-stab"]');
        const vertEye = vertItem ? vertItem.querySelector('.outliner-icon') : null;
        if (vertEye) {
            vertEye.click();
        }
        await new Promise(r => setTimeout(r, 60));
        
        const inSetHoriz = App.ui.viewParams.isolatedSet.has('horiz-stab');
        const inSetVert = App.ui.viewParams.isolatedSet.has('vert-stab');
        
        const horizEye = document.querySelector('#comp-list .outliner-item[data-id="horiz-stab"] .outliner-icon');
        const vertEyeNew = document.querySelector('#comp-list .outliner-item[data-id="vert-stab"] .outliner-icon');
        
        const groups = Array.from(document.querySelectorAll('#components-layer g.interactive-shape'));
        const opacities = groups.map(g => g.style.opacity || '1');
        
        return {
            inSetHoriz,
            inSetVert,
            horizEyeOpacity: horizEye ? horizEye.style.opacity : 'none',
            vertEyeOpacity: vertEyeNew ? vertEyeNew.style.opacity : 'none',
            numGhosted: opacities.filter(o => o === '0.15').length,
            numFull: opacities.filter(o => o !== '0.15').length
        };
    })()
    """)

    print(f"[{label}] After clicking eye icon of vert-stab:")
    print(f"  vert-stab in isolatedSet: {click_eye_state['inSetVert']}")
    print(f"  vert-stab eye icon opacity: {click_eye_state['vertEyeOpacity']} (expected '1')")
    print(f"  Canvas components: {click_eye_state['numFull']} full, {click_eye_state['numGhosted']} ghosted")

    assert click_eye_state['inSetVert'] is True, "vert-stab must now be in isolatedSet"
    assert click_eye_state['vertEyeOpacity'] == '1', f"vert-stab eye icon must now be 1, got {click_eye_state['vertEyeOpacity']}"
    assert click_eye_state['numFull'] > init_state['numFull'], "Fully visible components count must increase"

    # Screenshot 2: Both horiz-stab and vert-stab fully visible
    shot2 = await send_cmd("Page.captureScreenshot", {"format": "png"})
    Path(f"C:/Users/Victor/.gemini/antigravity/brain/aeb4bcd8-b84f-461d-a02c-750035953491/{screenshot_prefix}_eye_clicked.png").write_bytes(base64.b64decode(shot2["result"]["data"]))

    # 3. Click the eye icon of vert-stab again to toggle back to transparent
    toggle_back_state = await eval_js("""
    (async () => {
        const vertEye = document.querySelector('#comp-list .outliner-item[data-id="vert-stab"] .outliner-icon');
        if (vertEye) vertEye.click();
        await new Promise(r => setTimeout(r, 60));
        
        return {
            inSetVert: App.ui.viewParams.isolatedSet.has('vert-stab'),
            vertEyeOpacity: document.querySelector('#comp-list .outliner-item[data-id="vert-stab"] .outliner-icon').style.opacity
        };
    })()
    """)

    print(f"[{label}] After clicking eye icon again:")
    print(f"  vert-stab in isolatedSet: {toggle_back_state['inSetVert']}")
    print(f"  vert-stab eye icon opacity: {toggle_back_state['vertEyeOpacity']} (expected '0.2')")
    assert toggle_back_state['inSetVert'] is False, "vert-stab should no longer be in isolatedSet"
    assert toggle_back_state['vertEyeOpacity'] == '0.2', "vert-stab eye icon should dim to 0.2"

    # 4. Exit isolated mode with 'i'
    exit_state = await eval_js("""
    (async () => {
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'i', code: 'KeyI', bubbles: true }));
        await new Promise(r => setTimeout(r, 60));
        const wingPoly = document.querySelector('#wing-layer path, #wing-layer polygon');
        const wingOpacity = wingPoly ? (wingPoly.style.opacity || '1') : '1';
        return {
            isIsolated: App.ui.viewParams.isIsolated,
            wingOpacity
        };
    })()
    """)
    print(f"[{label}] After exiting isolation:")
    print(f"  isIsolated: {exit_state['isIsolated']}")
    print(f"  Wing opacity: {exit_state['wingOpacity']}")
    assert exit_state['isIsolated'] is False, "Must exit isolated mode"
    assert exit_state['wingOpacity'] in ('', '1'), "Wing must be back to full opacity"
    print(f"[{label}] ==> ISOLATED MODE TESTS PASSED!")

async def main():
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

            s_url = Path("Aircraft Design Tool S01.9.html").resolve().as_uri()
            await test_file_isolate(ws, s_url, "Version S01.9", "s01_9")

            w_url = Path("Aircraft Design Tool W1.0.html").resolve().as_uri()
            await test_file_isolate(ws, w_url, "Version W1.0 (Aero)", "w1_0")

            print("\n=======================================================")
            print("SUCCESS: ALL ISOLATED MODE TESTS PASSED FOR S01.9 & W1.0!")
            print("=======================================================")
    finally:
        proc.terminate()
        proc.wait()

if __name__ == "__main__":
    asyncio.run(main())
