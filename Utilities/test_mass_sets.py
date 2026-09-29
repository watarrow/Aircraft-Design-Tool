import asyncio
import json
import os
import subprocess
import urllib.request
import websockets
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

PORT = 9245
USER_DATA = "C:/tmp/edge_cdp_test_mass_sets"
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
                    data = json.loads(r)
                    if data.get("id") == msg_id:
                        return data

            async def eval_js(expr):
                res = await send_cmd("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
                return res.get("result", {}).get("result", {}).get("value")

            print("Evaluating initial mass profile state...")
            initial_active = await eval_js("App.state.activeMassProfile")
            initial_profiles = await eval_js("App.state.massProfiles")
            print(f"Initial active: {initial_active}, profiles: {initial_profiles}")
            assert initial_active == "budget", f"Expected budget, got {initial_active}"
            assert initial_profiles == ["budget", "measured", "predicted"]

            sizes = await eval_js("""
                (() => {
                    const top = document.getElementById('view-btn-top').getBoundingClientRect();
                    const b = document.getElementById('btn-profile-budget').getBoundingClientRect();
                    const a = document.getElementById('btn-profile-add').getBoundingClientRect();
                    const d = document.getElementById('btn-profile-del').getBoundingClientRect();
                    return {
                        topBtn: { w: top.width, h: top.height },
                        budget: { w: b.width, h: b.height },
                        add: { w: a.width, h: a.height },
                        del: { w: d.width, h: d.height }
                    };
                })()
            """)
            print("BUTTON SIZES CURRENTLY:", sizes)

            # Test 1: Click 'Measured' button via DOM click
            print("\nTest 1: Clicking Measured button...")
            click_measured = await eval_js("""
                (async () => {
                    const btn = document.getElementById('btn-profile-measured');
                    if (!btn) return 'not found';
                    btn.click();
                    await new Promise(r => setTimeout(r, 50));
                    return {
                        clicked: true,
                        activeProfile: App.state.activeMassProfile,
                        hasActiveClass: btn.classList.contains('active'),
                        budgetHasActive: document.getElementById('btn-profile-budget').classList.contains('active')
                    };
                })()
            """)
            print("Click Measured result:", click_measured)
            assert click_measured["activeProfile"] == "measured", f"Expected activeProfile measured, got {click_measured}"
            assert click_measured["hasActiveClass"] is True
            assert click_measured["budgetHasActive"] is False

            # Test 2: Click 'Predicted' button via DOM click
            print("\nTest 2: Clicking Predicted button...")
            click_predicted = await eval_js("""
                (async () => {
                    const btn = document.getElementById('btn-profile-predicted');
                    if (!btn) return 'not found';
                    btn.click();
                    await new Promise(r => setTimeout(r, 50));
                    return {
                        clicked: true,
                        activeProfile: App.state.activeMassProfile,
                        hasActiveClass: btn.classList.contains('active')
                    };
                })()
            """)
            print("Click Predicted result:", click_predicted)
            assert click_predicted["activeProfile"] == "predicted"
            assert click_predicted["hasActiveClass"] is True

            # Test 3: Click 'Budget' button via DOM click to switch back
            print("\nTest 3: Clicking Budget button...")
            click_budget = await eval_js("""
                (async () => {
                    const btn = document.getElementById('btn-profile-budget');
                    btn.click();
                    await new Promise(r => setTimeout(r, 50));
                    return {
                        activeProfile: App.state.activeMassProfile,
                        hasActiveClass: btn.classList.contains('active')
                    };
                })()
            """)
            print("Click Budget result:", click_budget)
            assert click_budget["activeProfile"] == "budget"
            assert click_budget["hasActiveClass"] is True

            # Test 4: Test '+' Add Button (simulate prompt response)
            print("\nTest 4: Clicking '+' button to add custom profile 'FlightTest'...")
            add_result = await eval_js("""
                (async () => {
                    // Mock window.prompt and window.confirm
                    window.prompt = () => 'FlightTest';
                    window.confirm = () => true;
                    
                    const addBtn = document.getElementById('btn-profile-add');
                    if (!addBtn) return { error: 'No addBtn' };
                    addBtn.click();
                    await new Promise(r => setTimeout(r, 50));
                    
                    const newBtn = document.getElementById('btn-profile-FlightTest');
                    return {
                        profiles: App.state.massProfiles,
                        activeProfile: App.state.activeMassProfile,
                        newBtnExists: !!newBtn,
                        newBtnActive: newBtn ? newBtn.classList.contains('active') : false
                    };
                })()
            """)
            print("Add result:", add_result)
            assert "FlightTest" in add_result["profiles"]
            assert add_result["activeProfile"] == "FlightTest"
            assert add_result["newBtnExists"] is True
            assert add_result["newBtnActive"] is True

            # Test 5: Switch to Measured, then click custom profile FlightTest button
            print("\nTest 5: Switching to Measured, then clicking FlightTest button...")
            switch_back = await eval_js("""
                (async () => {
                    document.getElementById('btn-profile-measured').click();
                    await new Promise(r => setTimeout(r, 50));
                    const state1 = App.state.activeMassProfile;
                    document.getElementById('btn-profile-FlightTest').click();
                    await new Promise(r => setTimeout(r, 50));
                    const state2 = App.state.activeMassProfile;
                    return { state1, state2, btnActive: document.getElementById('btn-profile-FlightTest').classList.contains('active') };
                })()
            """)
            print("Switch back and click custom result:", switch_back)
            assert switch_back["state1"] == "measured"
            assert switch_back["state2"] == "FlightTest"
            assert switch_back["btnActive"] is True

            # Test 6: Rename profile via dblclick
            print("\nTest 6: Renaming FlightTest to FlightBeta via dblclick...")
            rename_result = await eval_js("""
                (async () => {
                    window.prompt = () => 'FlightBeta';
                    const btn = document.getElementById('btn-profile-FlightTest');
                    btn.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
                    await new Promise(r => setTimeout(r, 50));
                    
                    const renamedBtn = document.getElementById('btn-profile-FlightBeta');
                    return {
                        profiles: App.state.massProfiles,
                        activeProfile: App.state.activeMassProfile,
                        renamedBtnExists: !!renamedBtn,
                        renamedBtnActive: renamedBtn ? renamedBtn.classList.contains('active') : false
                    };
                })()
            """)
            print("Rename result:", rename_result)
            assert "FlightBeta" in rename_result["profiles"]
            assert "FlightTest" not in rename_result["profiles"]
            assert rename_result["activeProfile"] == "FlightBeta"
            assert rename_result["renamedBtnExists"] is True

            # Test 7: Delete active custom profile using '-' button
            print("\nTest 7: Deleting FlightBeta using '-' button...")
            delete_result = await eval_js("""
                (async () => {
                    window.confirm = () => true;
                    const delBtn = document.getElementById('btn-profile-del');
                    delBtn.click();
                    await new Promise(r => setTimeout(r, 50));
                    
                    const oldBtn = document.getElementById('btn-profile-FlightBeta');
                    return {
                        profiles: App.state.massProfiles,
                        activeProfile: App.state.activeMassProfile,
                        oldBtnExists: !!oldBtn,
                        budgetActive: document.getElementById('btn-profile-budget').classList.contains('active')
                    };
                })()
            """)
            print("Delete result:", delete_result)
            assert "FlightBeta" not in delete_result["profiles"]
            assert delete_result["activeProfile"] == "budget"
            assert delete_result["oldBtnExists"] is False
            assert delete_result["budgetActive"] is True

            # Test 8: Verify deleting default profile is blocked
            print("\nTest 8: Verifying deletion of default profiles is blocked...")
            blocked_result = await eval_js("""
                (async () => {
                    let alertMsg = null;
                    window.alert = (msg) => { alertMsg = msg; };
                    const delBtn = document.getElementById('btn-profile-del');
                    delBtn.click();
                    await new Promise(r => setTimeout(r, 50));
                    return {
                        alertMsg,
                        activeProfile: App.state.activeMassProfile,
                        profiles: App.state.massProfiles
                    };
                })()
            """)
            print("Blocked result:", blocked_result)
            assert "cannot delete the default" in blocked_result["alertMsg"].lower()
            assert blocked_result["activeProfile"] == "budget"
            assert blocked_result["profiles"] == ["budget", "measured", "predicted"]

            # Test 9: Verify square button dimensions for '+' and '-'
            print("\nTest 9: Verifying '+' and '-' buttons are square (28x28px)...")
            btn_sizes = await eval_js("""
                (() => {
                    const add = document.getElementById('btn-profile-add').getBoundingClientRect();
                    const del = document.getElementById('btn-profile-del').getBoundingClientRect();
                    return {
                        add: { w: Math.round(add.width), h: Math.round(add.height) },
                        del: { w: Math.round(del.width), h: Math.round(del.height) }
                    };
                })()
            """)
            print("Button sizes:", btn_sizes)
            assert btn_sizes["add"]["w"] == 28 and btn_sizes["add"]["h"] == 28, f"Expected 28x28, got {btn_sizes['add']}"
            assert btn_sizes["del"]["w"] == 28 and btn_sizes["del"]["h"] == 28, f"Expected 28x28, got {btn_sizes['del']}"

            print("\nALL MASS SET TESTS PASSED SUCCESSFULLY! 100% verified.")

    finally:
        proc.terminate()

if __name__ == "__main__":
    asyncio.run(main())
