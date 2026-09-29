import os
import sys
import json
import time
import subprocess
import urllib.request
from pathlib import Path
import asyncio

HTML_PATH = r"c:\Users\Victor\Documents\Projects\Aircraft-Design-Tool\Aircraft Design Tool S01.8.html"
FILE_URL = Path(HTML_PATH).as_uri()
EDGE_EXE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9222

async def run_cdp_tests():
    import websockets
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
                if res.get("method") == "Runtime.exceptionThrown":
                    print("PAGE EXCEPTION:", json.dumps(res["params"]))
                if res.get("id") == msg_id:
                    return res

        await send_cmd("Runtime.enable")
        await send_cmd("Page.enable")
        await send_cmd("Console.enable")

        async def eval_js(expression):
            res = await send_cmd("Runtime.evaluate", {"expression": expression, "returnByValue": True})
            if "exceptionDetails" in res.get("result", {}):
                raise RuntimeError(f"JS Exception: {res['result']['exceptionDetails']}")
            return res.get("result", {}).get("result", {}).get("value")

        print("Navigating to:", FILE_URL)
        await send_cmd("Page.navigate", {"url": FILE_URL})
        await asyncio.sleep(3)

        current_url = await eval_js("window.location.href")
        print("Loaded page URL:", current_url)

        # 1. Check for basic DOM elements
        has_dim_btn = await eval_js("!!document.getElementById('tool-btn-dim')")
        has_dim_layer = await eval_js("!!document.getElementById('dimensions-layer')")
        has_popover = await eval_js("!!document.getElementById('dim-edit-popover')")
        print(f"Elements: btn={has_dim_btn}, layer={has_dim_layer}, popover={has_popover}")
        assert has_dim_btn and has_dim_layer and has_popover, "DOM elements missing"

        # Check button position: between Front View and Graph Sweep
        dim_btn_prev = await eval_js("document.getElementById('tool-btn-dim').previousElementSibling ? document.getElementById('tool-btn-dim').previousElementSibling.innerText.trim() : ''")
        dim_btn_next = await eval_js("document.getElementById('tool-btn-dim').nextElementSibling ? document.getElementById('tool-btn-dim').nextElementSibling.innerText.trim() : ''")
        print("Dim button prev sibling text:", dim_btn_prev, "next:", dim_btn_next)
        assert dim_btn_prev == "Front View", f"Expected prev sibling Front View, found: {dim_btn_prev}"
        assert dim_btn_next == "Graph Sweep", f"Expected next sibling Graph Sweep, found: {dim_btn_next}"

        # Check shortcuts legend has 'D' Dimension
        legend_html = await eval_js("document.getElementById('shortcuts-legend').innerHTML")
        assert "Dimension" in legend_html and ">D<" in legend_html, "Shortcuts legend missing D Dimension"

        # 2. Test toggleDimensionTool()
        tool_active_1 = await eval_js("toggleDimensionTool(); App.state.dimTool.active")
        btn_has_class = await eval_js("document.getElementById('tool-btn-dim').classList.contains('active')")
        btn_no_old_class = await eval_js("!document.getElementById('tool-btn-dim').classList.contains('tool-active')")
        tool_active_2 = await eval_js("toggleDimensionTool(); App.state.dimTool.active")
        print(f"Tool toggle: active={tool_active_1}, btnActive={btn_has_class}, noOldClass={btn_no_old_class}, deactivated={not tool_active_2}")
        assert tool_active_1 and btn_has_class and btn_no_old_class and not tool_active_2, "Dimension tool toggle failed"

        # Test Keyboard shortcut 'd'
        await eval_js("window.dispatchEvent(new KeyboardEvent('keydown', { key: 'd', bubbles: true }))")
        shortcut_active = await eval_js("App.state.dimTool.active")
        assert shortcut_active, "Keyboard shortcut 'd' failed to activate dimension tool"
        await eval_js("window.dispatchEvent(new KeyboardEvent('keydown', { key: 'd', bubbles: true }))")
        shortcut_inactive = await eval_js("!App.state.dimTool.active")
        assert shortcut_inactive, "Keyboard shortcut 'd' failed to deactivate dimension tool"

        # 3. Test interactive placement via handleDimToolClick & finalizeDimensionPlacement
        await eval_js("toggleDimensionTool(true);")
        # Step 0: click wing
        await eval_js("handleDimToolClick(null, 'main-wing');")
        step_1 = await eval_js("App.state.dimTool.step")
        ref_a = await eval_js("App.state.dimTool.refA")
        part_a_id = ref_a if isinstance(ref_a, str) else ref_a.get('partId')
        assert step_1 == 1 and part_a_id == 'main-wing', f"Step 1 failed: step={step_1}, refA={ref_a}"

        # Find first non-wing active component
        comp_id = await eval_js("App.state.components[0].id")
        comp_name = await eval_js("App.state.components[0].name")
        print(f"Targeting component: {comp_name} ({comp_id})")

        # Step 1: click component
        await eval_js(f"handleDimToolClick(null, '{comp_id}');")
        step_2 = await eval_js("App.state.dimTool.step")
        ref_b = await eval_js("App.state.dimTool.refB")
        part_b_id = ref_b if isinstance(ref_b, str) else ref_b.get('partId')
        assert step_2 == 2 and part_b_id == comp_id, f"Step 2 failed: step={step_2}, refB={ref_b}"

        # Wait past the debounce period (200ms)
        await asyncio.sleep(0.25)

        # Step 2: finalize placement at SVG position (u=50, v=25)
        await eval_js("App.state.dimTool.previewPos = { u: 50, v: 25 }; finalizeDimensionPlacement(null);")
        dims_count = await eval_js("getActiveDimensions().length")
        dim_obj = await eval_js("getActiveDimensions()[0]")
        print(f"Dimension placed: count={dims_count}, dim={dim_obj}")
        assert dims_count == 1, "Dimension was not created"
        assert dim_obj["partA"] == "main-wing" and dim_obj["partB"] == comp_id, "Parts mismatch"

        # 4. Test driving dimension updates component position
        initial_x = await eval_js(f"getPartCenterCoord(App.state.components.find(c => c.id === '{comp_id}'), 'x')")
        print(f"Initial X center: {initial_x}")

        # Modify dimension to 75.0 (internal cm)
        new_target_dist = 75.0
        await eval_js(f"applyDrivingDimension(getActiveDimensions()[0], {new_target_dist});")
        updated_x = await eval_js(f"getPartCenterCoord(App.state.components.find(c => c.id === '{comp_id}'), 'x')")
        print(f"Updated X center after driving dim: {updated_x}")
        assert abs(updated_x - new_target_dist) < 0.001, f"Component position was not driven correctly! Expected {new_target_dist}, got {updated_x}"

        # Check properties panel sync
        await eval_js(f"handleSelectComponent('{comp_id}'); renderInspector();")
        prop_x_val = await eval_js("parseFloat(document.getElementById('prop-x').value)")
        d_scale = await eval_js("getDimScalar()")
        expected_prop_x = round(new_target_dist * d_scale, 2)
        print(f"Inspector prop-x: {prop_x_val}, expected: {expected_prop_x}")
        assert abs(prop_x_val - expected_prop_x) < 0.05, f"Inspector prop-x mismatch: {prop_x_val} vs {expected_prop_x}"

        # 5. Test popover modify UI
        await eval_js(f"openDimensionModifyDialog(getActiveDimensions()[0].id);")
        popover_visible = await eval_js("document.getElementById('dim-edit-popover').style.display !== 'none'")
        popover_val = await eval_js("parseFloat(document.getElementById('dim-input-val').value)")
        print(f"Popover opened: visible={popover_visible}, value={popover_val}")
        assert popover_visible and abs(popover_val - expected_prop_x) < 0.05, "Popover failed to load current value"

        # Change value via popover
        new_user_input = 82.5 * d_scale
        await eval_js(f"document.getElementById('dim-input-val').value = '{new_user_input}'; confirmDimensionModify();")
        final_x = await eval_js(f"getPartCenterCoord(App.state.components.find(c => c.id === '{comp_id}'), 'x')")
        print(f"Final X center after popover confirm: {final_x}")
        assert abs(final_x - 82.5) < 0.001, f"Popover driving modify failed: {final_x}"

        # 6. Test configuration inheritance and overrides
        # Create Linked Variant
        await eval_js("executeConfigCreation(App.state.configurations[0], 'linked');")
        num_cfgs = await eval_js("App.state.configurations.length")
        linked_cfg = await eval_js("App.state.configurations[1]")
        print(f"Created Linked Variant: {linked_cfg['name']}, cfgs count={num_cfgs}")
        
        # Switch to Linked Variant using handleActivateConfig
        await eval_js("handleActivateConfig(App.state.configurations[1].id);")
        linked_dims_count = await eval_js("getActiveDimensions().length")
        print(f"Linked Variant dimensions count: {linked_dims_count}")
        assert linked_dims_count == 1, "Linked Variant should inherit dimensions from Base"

        # Drive position in Linked Variant
        await eval_js(f"applyDrivingDimension(getActiveDimensions()[0], 90.0);")
        linked_comp_x = await eval_js(f"getPartCenterCoord(App.state.components.find(c => c.id === '{comp_id}'), 'x')")
        print(f"Linked Variant comp X: {linked_comp_x}")
        assert abs(linked_comp_x - 90.0) < 0.001, "Linked Variant position drive failed"

        # Switch back to Base Configuration using handleActivateConfig
        await eval_js("handleActivateConfig(App.state.configurations[0].id);")
        base_comp_x = await eval_js(f"getPartCenterCoord(App.state.components.find(c => c.id === '{comp_id}'), 'x')")
        print(f"Base Configuration comp X: {base_comp_x}")
        assert abs(base_comp_x - 82.5) < 0.001, f"Base Configuration should remain unaffected: {base_comp_x}"

        # 7. Test Unique Duplicate
        await eval_js("executeConfigCreation(App.state.configurations[0], 'unique');")
        unique_dims_count = await eval_js("App.state.configurations[2].dimensions.length")
        unique_dim_id = await eval_js("App.state.configurations[2].dimensions[0].id")
        base_dim_id = await eval_js("App.state.configurations[0].dimensions[0].id")
        print(f"Unique duplicate: dimCount={unique_dims_count}, uniqueDimId={unique_dim_id}, baseDimId={base_dim_id}")
        assert unique_dims_count == 1 and unique_dim_id != base_dim_id, "Unique duplicate dimensions failed"

        # 8. Test Blank Config
        await eval_js("executeConfigCreation(App.state.configurations[0], 'blank');")
        blank_dims_count = await eval_js("App.state.configurations[3].dimensions.length")
        print(f"Blank config: dimCount={blank_dims_count}")
        assert blank_dims_count == 0, "Blank config should have 0 dimensions"

        # 9. Test deleteDimension()
        await eval_js("deleteDimension(getActiveDimensions()[0].id);")
        remaining_dims = await eval_js("getActiveDimensions().length")
        print(f"Remaining dimensions after delete: {remaining_dims}")
        assert remaining_dims == 0, "Dimension delete failed"

        # 10. Test Parallel Edges Dimensioning (Perpendicular Distance Locking)
        print("\n--- Testing Parallel Edges Dimensioning ---")
        await eval_js("toggleDimensionTool(true);")
        # Get selectable features for top view
        feats_edges = await eval_js("getSelectableFeatures('top').edges")
        tip_left = next((e for e in feats_edges if e["partId"] == "main-wing" and e["featureId"] == "tip_left"), None)
        tip_right = next((e for e in feats_edges if e["partId"] == "main-wing" and e["featureId"] == "tip_right"), None)
        assert tip_left and tip_right, "Wing tip edges not found in selectable features"

        # Select first edge: tip_left
        await eval_js(f"App.state.dimTool.step = 0; handleDimToolClick(null, null, {json.dumps(tip_left)});")
        p_step1 = await eval_js("App.state.dimTool.step")
        ref_a = await eval_js("App.state.dimTool.refA")
        assert p_step1 == 1 and ref_a["featureId"] == "tip_left", f"Step 1 failed for parallel edge: step={p_step1}"

        # Select second parallel edge: tip_right
        await eval_js(f"handleDimToolClick(null, null, {json.dumps(tip_right)});")
        p_step2 = await eval_js("App.state.dimTool.step")
        ref_b = await eval_js("App.state.dimTool.refB")
        assert p_step2 == 2 and ref_b["featureId"] == "tip_right", f"Step 2 failed for parallel edge: step={p_step2}"

        # Check checkParallelEdges in JS returns isParallel and perpDist equal to wingspan (100)
        p_info = await eval_js("checkParallelEdges(App.state.dimTool.refA, App.state.dimTool.refB, 'top')")
        print(f"Parallel info: isParallel={p_info.get('isParallel')}, perpDist={p_info.get('perpDist')}, isHorizontal={p_info.get('isHorizontal')}")
        assert p_info and p_info.get("isParallel"), "checkParallelEdges failed to identify parallel edges"
        expected_span = await eval_js("safeParse(App.state.wingData.b)")
        assert abs(p_info.get("perpDist") - expected_span) < 0.01, f"perpDist mismatch: {p_info.get('perpDist')} vs {expected_span}"

        # Test live preview rendering at various mouse positions
        for preview_u, preview_v in [(10, 0), (50, 40), (-20, -30)]:
            await eval_js(f"App.state.dimTool.previewPos = {{ u: {preview_u}, v: {preview_v} }}; renderAircraft();")
            prev_badge_text = await eval_js("document.querySelector('#dim-preview-group text')?.textContent")
            print(f"Preview at ({preview_u}, {preview_v}): badge='{prev_badge_text}'")
            assert f"{expected_span:.2f}" in prev_badge_text, f"Preview badge text '{prev_badge_text}' did not match span {expected_span}"

        # Finalize placement
        await asyncio.sleep(0.2)
        await eval_js("App.state.dimTool.previewPos = { u: 10, v: 0 }; finalizeDimensionPlacement(null);")
        p_dims = await eval_js("getActiveDimensions()")
        assert len(p_dims) == 1, "Parallel edge dimension was not added"
        p_dim = p_dims[0]
        assert p_dim.get("isParallelEdge") == True, "Dimension was not tagged as isParallelEdge"
        
        # Verify rendered SVG dimension group has correct perpendicular dimension elements
        dim_line = await eval_js("!!document.querySelector('.dim-group .dim-line')")
        dim_badge = await eval_js("document.querySelector('.dim-group .dim-badge text')?.textContent")
        print(f"Rendered parallel dimension: line={dim_line}, badge='{dim_badge}'")
        assert dim_line and f"{expected_span:.2f}" in dim_badge, "Parallel dimension did not render correctly in SVG"

        # Verify getDimensionDistance returns perpDist
        measured_dist = await eval_js(f"getDimensionDistance(getActiveDimensions()[0])")
        print(f"Measured distance via getDimensionDistance: {measured_dist}")
        assert abs(measured_dist - expected_span) < 0.01, f"Measured distance mismatch: {measured_dist} vs {expected_span}"

        # Clean up
        await eval_js("deleteDimension(getActiveDimensions()[0].id);")

        print("=== ALL 10 DRIVING & PARALLEL DIMENSION TESTS PASSED SUCCESSFULLY! ===")

def main():
    profile_dir = os.path.join(os.environ.get("TEMP", "."), "edge_test_profile_" + str(int(time.time())))
    os.makedirs(profile_dir, exist_ok=True)
    
    cmd = [
        EDGE_EXE,
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={profile_dir}",
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "about:blank"
    ]
    
    proc = subprocess.Popen(cmd)
    try:
        time.sleep(2.0)
        asyncio.run(run_cdp_tests())
    finally:
        proc.terminate()
        proc.wait()

if __name__ == "__main__":
    main()
