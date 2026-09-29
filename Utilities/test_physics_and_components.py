import asyncio
import json
import subprocess
import websockets
import requests

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
HTML_PATH = r"c:\Users\Victor\Documents\Projects\Aircraft-Design-Tool\Aircraft Design Tool S01.8.html"
FILE_URL = "file:///" + HTML_PATH.replace("\\", "/")

async def main():
    port = 9235
    proc = subprocess.Popen([
        EDGE_PATH,
        f"--remote-debugging-port={port}",
        "--headless=new",
        "--disable-gpu",
        "--window-size=1280,800",
        FILE_URL
    ])
    try:
        ws_url = None
        for _ in range(30):
            try:
                res = requests.get(f"http://127.0.0.1:{port}/json/list", timeout=1).json()
                page_tabs = [t for t in res if t.get("type") == "page"]
                if page_tabs:
                    ws_url = page_tabs[0].get("webSocketDebuggerUrl")
                    if ws_url:
                        break
            except Exception:
                pass
            await asyncio.sleep(0.2)
            
        assert ws_url, "Could not connect to Edge DevTools port"
        
        async with websockets.connect(ws_url) as ws:
            msg_id = 0
            async def eval_js(expr):
                nonlocal msg_id
                msg_id += 1
                await ws.send(json.dumps({"id": msg_id, "method": "Runtime.evaluate", "params": {"expression": expr, "returnByValue": True}}))
                while True:
                    resp = json.loads(await ws.recv())
                    if resp.get("id") == msg_id:
                        if "exceptionDetails" in resp.get("result", {}):
                            raise Exception(f"JS Error: {resp['result']['exceptionDetails']}")
                        return resp["result"]["result"].get("value")

            # Wait for App to load
            for _ in range(50):
                ready = await eval_js("document.readyState === 'complete' && typeof App !== 'undefined' && typeof createDefaultComponents === 'function'")
                if ready:
                    break
                await asyncio.sleep(0.2)

            # Test 1: Components count and schema
            comps = await eval_js("createDefaultComponents()")
            print(f"Default components count: {len(comps)}")
            assert len(comps) == 20, f"Expected 20 default components, got {len(comps)}"
            
            # Verify specific component properties
            c0 = comps[0]
            print(f"Component 0: {c0['name']}, type={c0['type']}, mass={c0['budgetMass']}")
            assert c0["id"] == "horiz-stab"
            assert c0["budgetMass"] == 24
            assert c0["rotY"] == -4
            assert len(c0["sections"]) == 2

            # Test 2: Calculate Aircraft metrics
            calc_metrics = await eval_js("""
                (() => {
                    calculateAircraft();
                    return {
                        globalCGX: App.state.globalCGX,
                        globalCGZ: App.state.globalCGZ,
                        rec_cg_33: App.state.rec_cg_33,
                        totalMass: parseFloat(document.getElementById('top-mass')?.dataset?.raw || 0),
                        twr: parseFloat(document.getElementById('top-twr')?.dataset?.raw || 0),
                        sm: parseFloat(document.getElementById('top-sm')?.dataset?.raw || 0),
                        vh: parseFloat(document.getElementById('top-vh')?.dataset?.raw || 0),
                        vv: parseFloat(document.getElementById('top-vv')?.dataset?.raw || 0)
                    };
                })()
            """)
            print("Calculated Aircraft Metrics:", json.dumps(calc_metrics, indent=2))
            assert calc_metrics["totalMass"] > 500, "Total mass should be > 500g"
            assert calc_metrics["globalCGX"] > 0, "Global CGX should be positive"

            # Test 3: getProp tests
            get_prop_test = await eval_js("""
                (() => {
                    const c = App.state.components[0];
                    return {
                        x: getProp(c, 'x'),
                        type: getProp(c, 'type'),
                        rotY: getProp(c, 'rotY')
                    };
                })()
            """)
            print("getProp test:", get_prop_test)
            assert get_prop_test["type"] == "hstab"

            print("\nBASELINE VERIFICATION SUCCESSFUL!")
            return calc_metrics

    finally:
        proc.kill()

if __name__ == "__main__":
    asyncio.run(main())
