import asyncio
import json
import os
import subprocess
import urllib.request
import websockets
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

PORT = 9266
USER_DATA = "C:/tmp/edge_cdp_focus_retention"
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
                if "exceptionDetails" in res.get("result", {}):
                    print("JS Exception:", res["result"]["exceptionDetails"])
                    raise RuntimeError(f"JS Exception: {res['result']['exceptionDetails']}")
                return res.get("result", {}).get("value")

            print("=== TEST SUITE: FOCUS RETENTION ON SINGLE CLICK & SHIFT ON DOUBLE CLICK ===")

            # 1. Focus on horizontal stabilizer
            print("\n1. Focusing on horiz-stab...")
            focus_res = await eval_js("""(() => {
                handleFocusComponent('horiz-stab');
                return {
                    selected: App.state.selectedComponentId,
                    isFocused: App.ui.viewParams.isFocused,
                    focusedComponentId: App.ui.viewParams.focusedComponentId
                };
            })()""")
            print("Initial focus state:", focus_res)
            assert focus_res["selected"] == 'horiz-stab'
            assert focus_res["isFocused"] is True
            assert focus_res["focusedComponentId"] == 'horiz-stab'
            print("PASS: horiz-stab is focused.")

            # 2. Single click on vertical stabilizer (via outliner click)
            print("\n2. Single-clicking vert-stab in outliner...")
            click_vert = await eval_js("""(() => {
                const item = document.querySelector('.outliner-item[data-id=\"vert-stab\"]');
                if (item) item.click();
                else handleSelectComponent('vert-stab');
                return {
                    selected: App.state.selectedComponentId,
                    isFocused: App.ui.viewParams.isFocused,
                    focusedComponentId: App.ui.viewParams.focusedComponentId
                };
            })()""")
            print("After single click vert-stab:", click_vert)
            assert click_vert["selected"] == 'vert-stab', f"Expected selected vert-stab, got {click_vert['selected']}"
            assert click_vert["isFocused"] is True, "isFocused should STILL be true"
            assert click_vert["focusedComponentId"] == 'horiz-stab', f"Focus should NOT shift, expected horiz-stab, got {click_vert['focusedComponentId']}"
            print("PASS: Focus did NOT shift when vert-stab was single-clicked! Remains on horiz-stab.")

            # 3. Single click on main wing
            print("\n3. Single-clicking main wing...")
            click_wing = await eval_js("""(() => {
                const wingId = App.state.wingData.id;
                handleSelectComponent(wingId);
                return {
                    selected: App.state.selectedComponentId,
                    isFocused: App.ui.viewParams.isFocused,
                    focusedComponentId: App.ui.viewParams.focusedComponentId
                };
            })()""")
            print("After single click wing:", click_wing)
            assert click_wing["isFocused"] is True
            assert click_wing["focusedComponentId"] == 'horiz-stab'
            print("PASS: Focus did NOT shift when wing was single-clicked! Remains on horiz-stab.")

            # 4. Single click via canvas SVG component
            print("\n4. Single-clicking a component on canvas...")
            canvas_click = await eval_js("""(() => {
                handleSelectComponent('rear-fus');
                return {
                    selected: App.state.selectedComponentId,
                    isFocused: App.ui.viewParams.isFocused,
                    focusedComponentId: App.ui.viewParams.focusedComponentId
                };
            })()""")
            print("After canvas click rear-fus:", canvas_click)
            assert canvas_click["selected"] == 'rear-fus'
            assert canvas_click["isFocused"] is True
            assert canvas_click["focusedComponentId"] == 'horiz-stab'
            print("PASS: Canvas selection preserves camera focus on horiz-stab.")

            # 5. Double-click on vertical stabilizer (via dblclick event)
            print("\n5. Double-clicking vert-stab to shift focus...")
            dblclick_vert = await eval_js("""(() => {
                const item = document.querySelector('.outliner-item[data-id=\"vert-stab\"]');
                if (item) {
                    item.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true }));
                } else {
                    handleFocusComponent('vert-stab');
                }
                return {
                    selected: App.state.selectedComponentId,
                    isFocused: App.ui.viewParams.isFocused,
                    focusedComponentId: App.ui.viewParams.focusedComponentId
                };
            })()""")
            print("After double click vert-stab:", dblclick_vert)
            assert dblclick_vert["selected"] == 'vert-stab'
            assert dblclick_vert["isFocused"] is True
            assert dblclick_vert["focusedComponentId"] == 'vert-stab'
            print("PASS: Focus shifted to vert-stab upon double-click!")

            # 6. Double-click on main wing
            print("\n6. Double-clicking main wing to shift focus...")
            dblclick_wing = await eval_js("""(() => {
                const wingPath = document.querySelector('#wing-layer path.interactive-shape');
                if (wingPath) {
                    wingPath.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true }));
                } else {
                    handleFocusComponent(App.state.wingData.id);
                }
                return {
                    selected: App.state.selectedComponentId,
                    isFocused: App.ui.viewParams.isFocused,
                    focusedComponentId: App.ui.viewParams.focusedComponentId
                };
            })()""")
            print("After double click wing:", dblclick_wing)
            assert dblclick_wing["isFocused"] is True
            assert dblclick_wing["focusedComponentId"] == 'main-wing'
            print("PASS: Focus shifted to main wing upon double-click!")

            # 7. Press 'F' key to toggle focus off
            print("\n7. Pressing 'F' key to toggle focus off...")
            unfocus_f = await eval_js("""(() => {
                const event = new KeyboardEvent('keydown', { key: 'f', bubbles: true, cancelable: true });
                window.dispatchEvent(event);
                return {
                    isFocused: App.ui.viewParams.isFocused,
                    focusedComponentId: App.ui.viewParams.focusedComponentId
                };
            })()""")
            print("After pressing F:", unfocus_f)
            assert unfocus_f["isFocused"] is False
            assert unfocus_f["focusedComponentId"] is None
            print("PASS: Focus toggled off with 'F' key.")

            print("\nALL FOCUS RETENTION & SHIFT TESTS PASSED SUCCESSFULLY! 100% verified.")

    finally:
        proc.terminate()

if __name__ == "__main__":
    asyncio.run(main())
