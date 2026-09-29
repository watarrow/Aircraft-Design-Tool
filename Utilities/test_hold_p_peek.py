import asyncio
import json
import os
import subprocess
import urllib.request
import websockets
import base64
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

PORT = 9260
USER_DATA = "C:/tmp/edge_cdp_hold_p_peek"
HTML_PATH = os.path.abspath(r"c:\Users\Victor\Documents\Projects\Aircraft-Design-Tool\Aircraft Design Tool S01.8.html")
FILE_URL = f"file:///{HTML_PATH.replace(os.sep, '/')}"
EDGE_EXE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
ARTIFACT_DIR = r"C:\Users\Victor\.gemini\antigravity\brain\aeb4bcd8-b84f-461d-a02c-750035953491"

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

            print("=== TEST SUITE: HOLD P TO PEEK AT PREVIOUS PROPERTIES PANEL ===")

            # 1. Initial State Check
            init_state = await eval_js("""(() => {
                return {
                    current: App.ui.panelHistory?.current,
                    previous: App.ui.panelHistory?.previous,
                    isWingVisible: document.getElementById('props-wing')?.style.display !== 'none',
                    isCalcVisible: document.getElementById('props-calc')?.style.display === 'flex'
                };
            })()""")
            print("1. Initial state:", init_state)
            assert init_state["isWingVisible"] is True, "Wing should be visible initially"
            assert init_state["previous"] is None, "Previous should be null initially"

            # 2. Open WL Calculator & Focus input
            calc_state = await eval_js("""(() => {
                document.getElementById('top-wl-box').click();
                const massInput = document.getElementById('calc-input-wl-mass');
                if (massInput) {
                    massInput.focus();
                    massInput.value = '1200';
                    massInput.dispatchEvent(new Event('input', { bubbles: true }));
                }
                return {
                    activeCalc: App.ui.activeCalculator,
                    isCalcVisible: document.getElementById('props-calc')?.style.display === 'flex',
                    isWingVisible: document.getElementById('props-wing')?.style.display !== 'none',
                    prevSnapshot: App.ui.panelHistory?.previous,
                    activeElementId: document.activeElement ? document.activeElement.id : null
                };
            })()""")
            print("2. After opening WL Calculator:", calc_state)
            assert calc_state["activeCalc"] == 'wl', "Active calculator should be wl"
            assert calc_state["isCalcVisible"] is True, "Calculator should be visible"
            assert calc_state["isWingVisible"] is False, "Wing should be hidden"
            assert calc_state["prevSnapshot"]["selectedComponentId"] == 'main-wing'
            assert calc_state["activeElementId"] == 'calc-input-wl-mass'

            # 3. Press and Hold 'p' (keydown)
            peek_state = await eval_js("""(() => {
                const target = document.getElementById('calc-input-wl-mass');
                const event = new KeyboardEvent('keydown', { key: 'p', bubbles: true, cancelable: true });
                target.dispatchEvent(event);
                return {
                    isPeeking: App.ui.panelHistory?.isPeeking,
                    hasPeekingClass: document.getElementById('properties-panel')?.classList.contains('is-peeking'),
                    peekBadgeText: document.getElementById('peek-badge')?.innerText,
                    isWingVisible: document.getElementById('props-wing')?.style.display !== 'none',
                    isCalcVisible: document.getElementById('props-calc')?.style.display === 'flex',
                    headerText: document.getElementById('props-header')?.innerText,
                    wingSpan: document.getElementById('wing-b')?.value
                };
            })()""")
            print("3. While holding P:", peek_state)
            assert peek_state["isPeeking"] is True, "Should be in peek mode"
            assert peek_state["hasPeekingClass"] is True, "Properties panel should have is-peeking class"
            assert "[HOLDING P TO PEEK]" in (peek_state["peekBadgeText"] or "")
            assert peek_state["isWingVisible"] is True, "Wing panel should be visible while peeking"
            assert peek_state["isCalcVisible"] is False, "Calculator panel should be hidden while peeking"
            print("PASS: Successfully peeking at Wing properties panel while holding P.")

            # 4. Scroll while holding P
            scroll_state = await eval_js("""(() => {
                const panel = document.getElementById('properties-panel');
                panel.scrollTop = 150;
                return {
                    scrollTop: panel.scrollTop
                };
            })()""")
            print("4. Scrolled properties panel to:", scroll_state)

            # 5. Release 'p' (keyup)
            unpeek_state = await eval_js("""(() => {
                const event = new KeyboardEvent('keyup', { key: 'p', bubbles: true, cancelable: true });
                window.dispatchEvent(event);
                return {
                    isPeeking: App.ui.panelHistory?.isPeeking,
                    hasPeekingClass: document.getElementById('properties-panel')?.classList.contains('is-peeking'),
                    isWingVisible: document.getElementById('props-wing')?.style.display !== 'none',
                    isCalcVisible: document.getElementById('props-calc')?.style.display === 'flex',
                    activeCalc: App.ui.activeCalculator,
                    peekBadgeExists: !!document.getElementById('peek-badge')
                };
            })()""")
            print("5. After releasing P:", unpeek_state)
            assert unpeek_state["isPeeking"] is False, "Should exit peek mode"
            assert unpeek_state["hasPeekingClass"] is False
            assert unpeek_state["isWingVisible"] is False
            assert unpeek_state["isCalcVisible"] is True
            assert unpeek_state["activeCalc"] == 'wl'
            assert unpeek_state["peekBadgeExists"] is False
            print("PASS: Successfully restored WL calculator on P release.")

            # 6. Verify focus restoration after animation frame
            await asyncio.sleep(0.1)
            focus_state = await eval_js("""(() => {
                return {
                    activeElementId: document.activeElement ? document.activeElement.id : null,
                    val: document.getElementById('calc-input-wl-mass')?.value
                };
            })()""")
            print("6. Focus restored to:", focus_state)
            assert focus_state["activeElementId"] == 'calc-input-wl-mass'
            assert float(focus_state["val"]) == 1200.0
            print("PASS: Focus restored to mass input field with value intact.")

            # 7. Test Capital 'P'
            print("\n7. Testing Capital 'P'...")
            cap_peek = await eval_js("""(() => {
                const event = new KeyboardEvent('keydown', { key: 'P', bubbles: true, cancelable: true });
                window.dispatchEvent(event);
                const isPeeking = App.ui.panelHistory?.isPeeking;
                const eventUp = new KeyboardEvent('keyup', { key: 'P', bubbles: true, cancelable: true });
                window.dispatchEvent(eventUp);
                return { isPeeking, finalPeeking: App.ui.panelHistory?.isPeeking };
            })()""")
            print("Capital P result:", cap_peek)
            assert cap_peek["isPeeking"] is True
            assert cap_peek["finalPeeking"] is False
            print("PASS: Capital 'P' verified.")

            # 8. Check Shortcuts Legend text
            print("\n8. Checking Shortcuts Legend...")
            legend_html = await eval_js("""(() => {
                renderShortcutsLegend();
                const l = document.getElementById('shortcuts-legend');
                return l ? l.innerText : '';
            })()""")
            print("Shortcuts legend text:\n", legend_html)
            assert "Hold P" in legend_html, f"Expected 'Hold P' in legend, got: {legend_html}"
            print("PASS: Shortcuts legend displays 'Hold P'.")

            print("\nALL HOLD P TO PEEK TESTS PASSED SUCCESSFULLY! 100% verified.")

    finally:
        proc.terminate()

if __name__ == "__main__":
    asyncio.run(main())
