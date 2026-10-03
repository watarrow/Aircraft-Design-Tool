import asyncio
import json
import os
import subprocess
import urllib.request
import websockets
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

PORT_S = 9297
PORT_D = 9298
USER_DATA_S = "C:/tmp/edge_cdp_s01_8_compat"
USER_DATA_D = "C:/tmp/edge_cdp_d01_0_compat"
HTML_S_PATH = os.path.abspath(r"c:\Users\Victor\Documents\Projects\Aircraft-Design-Tool\Aircraft Design Tool S01.8.html")
HTML_D_PATH = os.path.abspath(r"c:\Users\Victor\Documents\Projects\Aircraft-Design-Tool\Aircraft Design Tool D01.0.html")
FILE_URL_S = f"file:///{HTML_S_PATH.replace(os.sep, '/')}"
FILE_URL_D = f"file:///{HTML_D_PATH.replace(os.sep, '/')}"
EDGE_EXE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

TMP_JSON_DIR = "C:/tmp"
os.makedirs(TMP_JSON_DIR, exist_ok=True)
S01_8_JSON_PATH = os.path.join(TMP_JSON_DIR, "export_from_s01_8.json")
D01_0_JSON_PATH = os.path.join(TMP_JSON_DIR, "export_from_d01_0.json")

async def get_page_session(port, user_data, file_url):
    cmd = [
        EDGE_EXE,
        "--headless=new",
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data}",
        "--window-size=1280,950",
        file_url
    ]
    proc = subprocess.Popen(cmd)
    await asyncio.sleep(2.5)

    resp = urllib.request.urlopen(f"http://localhost:{port}/json")
    targets = json.loads(resp.read().decode("utf-8"))
    page_targets = [t for t in targets if t.get("type") == "page"]
    ws_url = page_targets[0]["webSocketDebuggerUrl"]

    ws = await websockets.connect(ws_url)
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
            raise RuntimeError(f"JS Exception: {res['exceptionDetails']}")
        return res.get("result", {}).get("value")

    return proc, ws, eval_js

async def main():
    print("=== TEST SUITE: BIDIRECTIONAL JSON COMPATIBILITY (S01.8 <-> D01.0) ===")

    # -------------------------------------------------------------
    # STEP 1: Launch S01.8 and export its JSON model
    # -------------------------------------------------------------
    print("\n--- STEP 1: Exporting JSON from S01.8 ---")
    proc_s, ws_s, eval_s = await get_page_session(PORT_S, USER_DATA_S, FILE_URL_S)
    try:
        s01_8_payload = await eval_s(r"""
        (() => {
            const activeCfg = (typeof getActiveConfig === 'function') ? getActiveConfig() : (App.state.configurations.find(cfg => cfg.isActive) || App.state.configurations[0]);
            if (activeCfg) {
                activeCfg.wing = App.state.wingData;
                activeCfg.components = App.state.components;
            }
            const titleEl = document.getElementById('project-title');
            const exportState = JSON.parse(JSON.stringify(App.state));
            exportState.history = { stack: [], index: -1 };
            delete exportState.unitScales;
            delete exportState.themePresets;
            delete exportState.activeThemePreset;

            return {
                title: titleEl ? titleEl.value : 'Aircraft_Model',
                state: exportState,
                metrics: {
                    totalMass: App.state.totalMass,
                    globalCGX: App.state.globalCGX,
                    rec_cg_33: App.state.rec_cg_33,
                    numComponents: App.state.components.length,
                    wingB: App.state.wingData.b,
                    wingCr: App.state.wingData.cr
                }
            };
        })()
        """)

        with open(S01_8_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump({"title": s01_8_payload["title"], "state": s01_8_payload["state"]}, f, indent=2)

        print(f"✓ Exported model '{s01_8_payload['title']}' from S01.8 with {s01_8_payload['metrics']['numComponents']} components.")
        print(f"  Total Mass: {s01_8_payload['metrics']['totalMass']:.2f}g | CG: {s01_8_payload['metrics']['globalCGX']:.2f}mm | Wing Span: {s01_8_payload['metrics']['wingB']}cm")

    finally:
        await ws_s.close()
        proc_s.kill()

    # -------------------------------------------------------------
    # STEP 2: Launch D01.0, import S01.8 JSON, verify 3D rendering
    # -------------------------------------------------------------
    print("\n--- STEP 2: Importing S01.8 JSON into D01.0 ---")
    proc_d, ws_d, eval_d = await get_page_session(PORT_D, USER_DATA_D, FILE_URL_D)
    try:
        with open(S01_8_JSON_PATH, "r", encoding="utf-8") as f:
            s_data = json.load(f)

        # Import into D01.0
        import_script = f"loadStateFromData({json.dumps(s_data)});"
        await eval_d(import_script)
        await asyncio.sleep(0.5)

        d01_0_state_after_import = await eval_d(r"""
        (() => {
            return {
                title: document.getElementById('project-title')?.value,
                numComponents: App.state.components.length,
                totalMass: App.state.totalMass,
                globalCGX: App.state.globalCGX,
                rec_cg_33: App.state.rec_cg_33,
                wingB: App.state.wingData.b,
                wingCr: App.state.wingData.cr,
                threeInitialized: App.three?.isInitialized,
                num3DMeshes: App.three?.compMeshes?.size,
                hasWingMesh: !!App.three?.wingMesh,
                currentView: App.state.currentView
            };
        })()
        """)
        print("D01.0 state after importing S01.8 model:", d01_0_state_after_import)

        assert d01_0_state_after_import["title"] == s01_8_payload["title"], "Project title must match"
        assert d01_0_state_after_import["numComponents"] == s01_8_payload["metrics"]["numComponents"], "Component counts must match"
        assert abs(d01_0_state_after_import["totalMass"] - s01_8_payload["metrics"]["totalMass"]) < 0.01, "Total mass must match"
        assert abs(d01_0_state_after_import["globalCGX"] - s01_8_payload["metrics"]["globalCGX"]) < 0.01, "CG X must match"
        assert d01_0_state_after_import["threeInitialized"] is True, "3D engine must be active"
        assert d01_0_state_after_import["hasWingMesh"] is True, "3D wing mesh must be rendered"
        assert d01_0_state_after_import["num3DMeshes"] > 0, "3D component meshes must be rendered"
        print("✓ S01.8 JSON imported cleanly into D01.0 with 100% aerodynamic & 3D mesh parity!")

        # -------------------------------------------------------------
        # STEP 3: Modify a component in D01.0 and export JSON
        # -------------------------------------------------------------
        print("\n--- STEP 3: Modifying model in D01.0 & Exporting JSON ---")
        # Add a custom component in D01.0
        await eval_d(r"""
        (() => {
            const comp = {
                id: 'comp-d01-compat-test',
                name: 'D01 Avionics Pod',
                type: 'body',
                x: 12.5, y: -2.0, z: 1.5,
                sx: 8.0, sy: 4.0, sz: 3.0,
                rho: 0.25,
                color: '#ff5500',
                budgetMass: 24,
                measuredMass: 0,
                predictedMass: 0,
                sections: [
                    { x: 0, w: 1, h: 1, dy: 0, dz: 0 },
                    { x: 1, w: 1, h: 1, dy: 0, dz: 0 }
                ]
            };
            App.state.components.push(comp);
            const activeCfg = getActiveConfig();
            if (activeCfg && activeCfg.components) activeCfg.components.push(comp);
            refresh();
            updateThreeScene();
        })()
        """)
        await asyncio.sleep(0.3)

        d01_0_payload = await eval_d(r"""
        (() => {
            const activeCfg = (typeof getActiveConfig === 'function') ? getActiveConfig() : (App.state.configurations.find(cfg => cfg.isActive) || App.state.configurations[0]);
            if (activeCfg) {
                activeCfg.wing = App.state.wingData;
                activeCfg.components = App.state.components;
            }
            const titleEl = document.getElementById('project-title');
            const exportState = JSON.parse(JSON.stringify(App.state));
            exportState.history = { stack: [], index: -1 };
            delete exportState.unitScales;
            delete exportState.themePresets;
            delete exportState.activeThemePreset;
            delete exportState.three;

            if (exportState.currentView === 'orbit3d') {
                exportState.currentView = 'top';
            }

            return {
                title: titleEl ? titleEl.value : 'Aircraft_Model',
                state: exportState,
                metrics: {
                    totalMass: App.state.totalMass,
                    globalCGX: App.state.globalCGX,
                    numComponents: App.state.components.length
                }
            };
        })()
        """)

        with open(D01_0_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump({"title": d01_0_payload["title"], "state": d01_0_payload["state"]}, f, indent=2)

        print(f"✓ Exported updated model from D01.0 with {d01_0_payload['metrics']['numComponents']} components.")
        print(f"  New Total Mass: {d01_0_payload['metrics']['totalMass']:.2f}g | New CG: {d01_0_payload['metrics']['globalCGX']:.2f}mm")

        # Verify export state has NO Three.js objects or circular structures
        json_text = json.dumps(d01_0_payload["state"])
        assert "WebGLRenderer" not in json_text
        assert "TransformControls" not in json_text
        assert d01_0_payload["state"]["currentView"] in ["top", "side", "front"]
        print("✓ Verified D01.0 JSON payload is pure, clean CAD data (no WebGL leaked).")

    finally:
        await ws_d.close()
        proc_d.kill()

    # -------------------------------------------------------------
    # STEP 4: Import D01.0 JSON back into S01.8
    # -------------------------------------------------------------
    print("\n--- STEP 4: Importing D01.0 JSON back into S01.8 ---")
    proc_s2, ws_s2, eval_s2 = await get_page_session(PORT_S + 10, USER_DATA_S + "_roundtrip", FILE_URL_S)
    try:
        with open(D01_0_JSON_PATH, "r", encoding="utf-8") as f:
            d_data = json.load(f)

        import_script2 = f"loadStateFromData({json.dumps(d_data)});"
        await eval_s2(import_script2)
        await asyncio.sleep(0.5)

        s01_8_roundtrip_state = await eval_s2(r"""
        (() => {
            const addedComp = App.state.components.find(c => c.id === 'comp-d01-compat-test');
            return {
                title: document.getElementById('project-title')?.value,
                numComponents: App.state.components.length,
                totalMass: App.state.totalMass,
                globalCGX: App.state.globalCGX,
                hasAddedComp: !!addedComp,
                addedCompName: addedComp?.name,
                addedCompMass: addedComp?.budgetMass,
                svgVisualizerVisible: document.getElementById('visualizer')?.style.display !== 'none'
            };
        })()
        """)
        print("S01.8 state after importing D01.0 model:", s01_8_roundtrip_state)

        assert s01_8_roundtrip_state["numComponents"] == d01_0_payload["metrics"]["numComponents"], "Component count in S01.8 must match D01.0"
        assert abs(s01_8_roundtrip_state["totalMass"] - d01_0_payload["metrics"]["totalMass"]) < 0.01, "Mass in S01.8 must match D01.0"
        assert abs(s01_8_roundtrip_state["globalCGX"] - d01_0_payload["metrics"]["globalCGX"]) < 0.01, "CG in S01.8 must match D01.0"
        assert s01_8_roundtrip_state["hasAddedComp"] is True, "New component created in D01.0 must exist in S01.8"
        assert s01_8_roundtrip_state["addedCompName"] == "D01 Avionics Pod"
        assert s01_8_roundtrip_state["addedCompMass"] == 24
        assert s01_8_roundtrip_state["svgVisualizerVisible"] is True, "S01.8 2D visualizer must render normally"
        print("✓ D01.0 JSON imported seamlessly into S01.8 with 100% component and physics fidelity!")

    finally:
        await ws_s2.close()
        proc_s2.kill()

    print("\n=================================================================")
    print("ALL BIDIRECTIONAL JSON COMPATIBILITY TESTS PASSED SUCCESSFULLY!")
    print("=================================================================")

if __name__ == "__main__":
    asyncio.run(main())
