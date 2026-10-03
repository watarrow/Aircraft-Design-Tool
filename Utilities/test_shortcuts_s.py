import os
import sys
import json
import time
import subprocess
import urllib.request
from pathlib import Path
import asyncio

EDGE_EXE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9225

async def test_file_shortcuts(ws, html_path, label):
    msg_id = 0
    async def send_cmd(method, params=None):
        nonlocal msg_id
        msg_id += 1
        payload = {"id": msg_id, "method": method, "params": params or {}}
        await ws.send(json.dumps(payload))
        while True:
            res = json.loads(await ws.recv())
            if res.get("method") == "Runtime.exceptionThrown":
                print(f"[{label}] PAGE EXCEPTION:", json.dumps(res["params"]))
            if res.get("id") == msg_id:
                return res

    async def eval_js(expression):
        res = await send_cmd("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        if "exceptionDetails" in res.get("result", {}):
            raise RuntimeError(f"JS Exception: {res['result']['exceptionDetails']}")
        return res.get("result", {}).get("result", {}).get("value")

    file_url = Path(html_path).as_uri()
    print(f"\n--- Testing {label} ({file_url}) ---")
    await send_cmd("Page.navigate", {"url": file_url})
    await asyncio.sleep(2.5)

    # 1. Test D shortcut to activate dimension mode
    print("1. Testing 'D' shortcut to activate dimension mode...")
    is_active_initial = await eval_js("!!(App.state.dimTool && App.state.dimTool.active)")
    assert not is_active_initial, "Dimension mode should be inactive initially"

    # Dispatch 'd' keydown
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'd', code: 'KeyD', bubbles: true }));
    """)
    is_active_after_d = await eval_js("!!(App.state.dimTool && App.state.dimTool.active)")
    print("Dimension active after D:", is_active_after_d)
    assert is_active_after_d, "Dimension mode should be activated on 'D'"

    # 2. Test Esc shortcut to deactivate dimension mode (even when step > 0)
    print("2. Testing 'Esc' shortcut to deactivate dimension mode...")
    # Set step to 1 (in progress)
    await eval_js("App.state.dimTool.step = 1;")
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true }));
    """)
    is_active_after_esc = await eval_js("!!(App.state.dimTool && App.state.dimTool.active)")
    print("Dimension active after Esc:", is_active_after_esc)
    assert not is_active_after_esc, "Dimension mode should be completely deactivated on 'Escape'"

    # 3. Test Ctrl+C and Ctrl+V to duplicate component
    print("3. Testing 'Ctrl+C' and 'Ctrl+V' to duplicate component...")
    # Select 'horiz-stab'
    await eval_js("handleSelectComponent('horiz-stab');")
    selected_id = await eval_js("App.state.selectedComponentId")
    assert selected_id == 'horiz-stab', "horiz-stab should be selected"
    initial_comp_count = await eval_js("App.state.components.length")

    # Press Ctrl+C
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'c', code: 'KeyC', ctrlKey: true, bubbles: true }));
    """)
    clipboard_id = await eval_js("App.clipboardComponentId")
    print("Clipboard component ID:", clipboard_id)
    assert clipboard_id == 'horiz-stab', f"Clipboard should contain 'horiz-stab', got {clipboard_id}"

    # Press Ctrl+V
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'v', code: 'KeyV', ctrlKey: true, bubbles: true }));
    """)
    new_comp_count = await eval_js("App.state.components.length")
    newly_selected = await eval_js("App.state.selectedComponentId")
    newly_selected_name = await eval_js("App.state.components.find(c => c.id === App.state.selectedComponentId)?.name")
    print(f"Components count: {initial_comp_count} -> {new_comp_count}, New part: {newly_selected} ({newly_selected_name})")
    assert new_comp_count == initial_comp_count + 1, "A new component should have been added"
    assert "(Copy)" in newly_selected_name, f"New component name should contain '(Copy)', got {newly_selected_name}"

    # 4. Test Shift+D to create instance
    print("4. Testing 'Shift+D' to create instance...")
    # Select 'vert-stab'
    await eval_js("handleSelectComponent('vert-stab');")
    comp_count_before_inst = await eval_js("App.state.components.length")

    # Press Shift+D
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'D', code: 'KeyD', shiftKey: true, bubbles: true }));
    """)
    comp_count_after_inst = await eval_js("App.state.components.length")
    inst_selected = await eval_js("App.state.selectedComponentId")
    inst_name = await eval_js("App.state.components.find(c => c.id === App.state.selectedComponentId)?.name")
    is_instance = await eval_js("!!App.state.components.find(c => c.id === App.state.selectedComponentId)?.parentId")
    print(f"Instance created: {inst_selected} ({inst_name}), hasParentId: {is_instance}")
    assert comp_count_after_inst == comp_count_before_inst + 1, "An instance component should have been created"
    assert "(Instance)" in inst_name, f"Instance name should contain '(Instance)', got {inst_name}"
    assert is_instance, "Created part must have parentId set"

    # 5. Test Enter to confirm dimension
    print("5. Testing 'Enter' to confirm dimension...")
    # 5A: Finalize placement with Enter when step == 2
    await eval_js("""
        toggleDimensionTool(true);
        App.state.dimTool.refA = { partId: 'main-wing', featureType: 'vertex', featureId: 'root_le', label: 'LE' };
        App.state.dimTool.refB = { partId: 'main-wing', featureType: 'vertex', featureId: 'root_te', label: 'TE' };
        App.state.dimTool.step = 2;
        App.state.dimTool.stepTransitionTime = 0; // bypass transition delay
    """)
    dim_count_before = await eval_js("getActiveDimensions().length")
    # Press Enter
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
    """)
    dim_count_after = await eval_js("getActiveDimensions().length")
    print(f"Dimension count after Enter placement: {dim_count_before} -> {dim_count_after}")
    assert dim_count_after == dim_count_before + 1, "Enter should finalize placing dimension in step 2"

    # 5B: Confirm dimension modification in popover with Enter
    print("5B. Testing Enter inside dimension modify dialog...")
    placed_dim_id = await eval_js("getActiveDimensions()[getActiveDimensions().length - 1].id")
    await eval_js(f"""
        openDimensionModifyDialog('{placed_dim_id}', 200, 200);
        document.getElementById('dim-input-val').value = '45.0';
    """)
    popover_display = await eval_js("document.getElementById('dim-edit-popover').style.display")
    assert popover_display != 'none', "Popover should be visible"

    # Press Enter
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
    """)
    popover_display_after = await eval_js("document.getElementById('dim-edit-popover').style.display")
    print("Popover display after Enter:", popover_display_after)
    assert popover_display_after == 'none', "Popover should be closed after Enter confirms"

    # Deactivate dimension tool after test
    await eval_js("toggleDimensionTool(false);")

    # 6. Test Shortcuts Legend reflects current shortcuts
    print("6. Testing Shortcuts Legend content...")
    await eval_js("handleSelectComponent('horiz-stab'); renderShortcutsLegend();")
    legend_html = await eval_js("document.getElementById('shortcuts-legend').innerHTML")
    assert "Ctrl+C / Ctrl+V" in legend_html, "Legend should mention Ctrl+C / Ctrl+V"
    assert "Shift+D" in legend_html, "Legend should mention Shift+D"
    assert "Dimension Mode" in legend_html or "Dimension" in legend_html, "Legend should mention Dimension"
    assert "Grab" in legend_html or "GRAB" in legend_html, "Legend should mention Grab"
    assert "Rotate" in legend_html or "ROTATE" in legend_html, "Legend should mention Rotate"
    assert "var(--accent-yellow)" not in legend_html, "Shortcuts legend should have colors removed (no accent-yellow)"
    assert "#e74c3c" not in legend_html, "Shortcuts legend should have colors removed (no #e74c3c)"

    # 7. Test dragging disabled by default
    print("7. Testing dragging disabled by default...")
    drag_enabled = await eval_js("App.ui.enableDragToMove")
    assert drag_enabled is False, "enableDragToMove should be false by default"
    checkbox_checked = await eval_js("document.getElementById('settings-drag-move')?.checked")
    assert checkbox_checked is False, "settings-drag-move checkbox should be unchecked by default"

    # Clicking component directly should not start dragging
    await eval_js("""
        App.state.drag.dragging = false;
        startDrag(new MouseEvent('mousedown', { clientX: 200, clientY: 200 }), 'horiz-stab');
    """)
    is_dragging = await eval_js("App.state.drag.dragging")
    assert not is_dragging, "Component should NOT start dragging when enableDragToMove is false"

    # Toggle enableDragToMove via checkbox
    await eval_js("""
        {
            const chk = document.getElementById('settings-drag-move');
            chk.checked = true;
            chk.dispatchEvent(new Event('change'));
        }
    """)
    drag_enabled_after = await eval_js("App.ui.enableDragToMove")
    assert drag_enabled_after is True, "enableDragToMove should be true after toggling checkbox"

    await eval_js("""
        startDrag(new MouseEvent('mousedown', { clientX: 200, clientY: 200 }), 'horiz-stab');
    """)
    is_dragging_after = await eval_js("App.state.drag.dragging")
    assert is_dragging_after, "Component should start dragging when enableDragToMove is true"

    # 7B. Test typing numbers while dragging moves part that distance in drag direction
    print("7B. Testing typing numbers while dragging moves part in drag direction...")
    init_drag_x = await eval_js("App.state.components.find(c => c.id === 'horiz-stab').x")
    # Simulate moving mouse rightwards during drag
    await eval_js("""
        doDrag(new MouseEvent('mousemove', { clientX: 250, clientY: 200 }));
    """)
    # Type '1', '5'
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: '1', code: 'Digit1', bubbles: true }));
        window.dispatchEvent(new KeyboardEvent('keydown', { key: '5', code: 'Digit5', bubbles: true }));
    """)
    drag_badge_text = await eval_js("document.getElementById('cursor-transform-badge')?.innerText")
    print(f"Drag cursor badge text after typing 15: '{drag_badge_text}'")
    assert "15" in drag_badge_text, f"Badge should show typed number 15, got {drag_badge_text}"
    typed_drag_x = await eval_js("App.state.components.find(c => c.id === 'horiz-stab').x")
    print(f"Displacement after typing 15 while dragging: {typed_drag_x - init_drag_x:.2f}")
    assert abs((typed_drag_x - init_drag_x) - 15) < 1e-1, f"Expected 15 displacement, got {typed_drag_x - init_drag_x}"
    # Confirm drag with Enter
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
    """)
    badge_after_enter = await eval_js("document.getElementById('cursor-transform-badge')")
    assert badge_after_enter is None, "Cursor badge should be removed after Enter confirms drag"
    drag_active_after = await eval_js("App.state.drag.dragging")
    assert not drag_active_after, "Dragging should end on Enter"

    # Re-disable drag to move
    await eval_js("""
        {
            App.state.drag.dragging = false;
            const chk = document.getElementById('settings-drag-move');
            chk.checked = false;
            chk.dispatchEvent(new Event('change'));
        }
    """)

    # 8. Test 'G' Grab mode with X/Y/Z axis constraints and Enter confirm
    print("8. Testing 'G' Grab mode with X/Y/Z axis constraints and Enter confirm...")
    await eval_js("handleSelectComponent('horiz-stab');")
    init_x, init_y, init_z = await eval_js("""
        (() => {
            const c = App.state.components.find(comp => comp.id === 'horiz-stab');
            return [c.x, c.y, c.z];
        })()
    """)

    # Press 'G'
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'g', code: 'KeyG', bubbles: true }));
    """)
    mt_mode = await eval_js("App.ui.modalTransform?.mode")
    assert mt_mode == 'grab', f"Modal transform should be 'grab', got {mt_mode}"

    # Press 'x' to constrain to X
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'x', code: 'KeyX', bubbles: true }));
    """)
    axis = await eval_js("App.ui.modalTransform?.axis")
    assert axis == 'x', f"Axis constraint should be 'x', got {axis}"

    # Verify bottom bar #modal-transform-hud is NOT present
    hud_el = await eval_js("document.getElementById('modal-transform-hud')")
    assert hud_el is None, "Bottom modal-transform-hud should be removed"

    # Verify #cursor-transform-badge is present
    badge_el = await eval_js("document.getElementById('cursor-transform-badge')")
    assert badge_el is not None, "Cursor transform badge should appear next to mouse cursor"

    # Simulate mouse movement in Grab mode (with delta in both u and v)
    await eval_js("""
        (() => {
            const svg = document.getElementById('visualizer');
            const pt = getSVGPoint(svg, 300, 300);
            updateModalTransformFromMouse({ u: App.ui.modalTransform.mouseStartCAD.u + 15, v: App.ui.modalTransform.mouseStartCAD.v + 25 });
        })()
    """)
    cur_x, cur_y, cur_z = await eval_js("""
        (() => {
            const c = App.state.components.find(comp => comp.id === 'horiz-stab');
            return [c.x, c.y, c.z];
        })()
    """)
    print(f"X-constrained Grab: dx={cur_x - init_x:.2f}, dy={cur_y - init_y:.2f}, dz={cur_z - init_z:.2f}")
    assert abs(cur_x - (init_x + 15)) < 1e-2, f"X should have increased by 15, got {cur_x - init_x}"
    assert abs(cur_y - init_y) < 1e-2, f"Y should NOT change when X is constrained, diff: {cur_y - init_y}"
    assert abs(cur_z - init_z) < 1e-2, f"Z should NOT change when X is constrained, diff: {cur_z - init_z}"

    # Press Enter to confirm transform
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
    """)
    final_x = await eval_js("App.state.components.find(comp => comp.id === 'horiz-stab').x")
    assert abs(final_x - (init_x + 15)) < 1e-2, "Position should be saved after Enter"

    # 8B. Test 'G' Grab mode with Ctrl (Snap 1cm) and Shift (Fine 0.2x)
    print("8B. Testing 'G' Grab mode with Ctrl (Snap) and Shift (Fine)...")
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'g', code: 'KeyG', bubbles: true }));
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'x', code: 'KeyX', bubbles: true }));
    """)
    base_x = await eval_js("App.ui.modalTransform.initialPos.x")

    # Move with Ctrl held: delta 12.35 -> should snap to 12.0
    await eval_js("""
        updateModalTransformFromMouse(
            { u: App.ui.modalTransform.mouseStartCAD.u + 12.35, v: App.ui.modalTransform.mouseStartCAD.v },
            { ctrlKey: true, shiftKey: false }
        );
    """)
    snap_x = await eval_js("App.state.components.find(comp => comp.id === 'horiz-stab').x")
    dx_ctrl = snap_x - base_x
    print(f"Ctrl snap displacement: {dx_ctrl:.2f} (expected 12.00)")
    assert abs(dx_ctrl - 12.0) < 1e-2, f"Ctrl should snap to 12.0, got {dx_ctrl}"

    # Move with Shift held: delta 10.0 -> fine precision 0.2x -> 2.0
    await eval_js("""
        updateModalTransformFromMouse(
            { u: App.ui.modalTransform.mouseStartCAD.u + 10.0, v: App.ui.modalTransform.mouseStartCAD.v },
            { ctrlKey: false, shiftKey: true }
        );
    """)
    fine_x = await eval_js("App.state.components.find(comp => comp.id === 'horiz-stab').x")
    dx_shift = fine_x - base_x
    print(f"Shift fine displacement: {dx_shift:.2f} (expected 2.00)")
    assert abs(dx_shift - 2.0) < 1e-2, f"Shift should scale to 2.0, got {dx_shift}"

    # Move with Ctrl+Shift held: delta 12.37 -> fine snap to 0.1 increments -> 12.4
    await eval_js("""
        updateModalTransformFromMouse(
            { u: App.ui.modalTransform.mouseStartCAD.u + 12.37, v: App.ui.modalTransform.mouseStartCAD.v },
            { ctrlKey: true, shiftKey: true }
        );
    """)
    cshift_x = await eval_js("App.state.components.find(comp => comp.id === 'horiz-stab').x")
    dx_cshift = cshift_x - base_x
    print(f"Ctrl+Shift fine snap displacement: {dx_cshift:.2f} (expected 12.40)")
    assert abs(dx_cshift - 12.4) < 1e-2, f"Ctrl+Shift should snap to 12.4, got {dx_cshift}"

    # Cancel modal transform to clean up
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true }));
    """)

    # 8C. Test typing numbers in Grab mode
    print("8C. Testing typing numbers in Grab mode...")
    x_before_8c = await eval_js("App.state.components.find(comp => comp.id === 'horiz-stab').x")
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'g', code: 'KeyG', bubbles: true }));
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'x', code: 'KeyX', bubbles: true }));
        window.dispatchEvent(new KeyboardEvent('keydown', { key: '2', code: 'Digit2', bubbles: true }));
        window.dispatchEvent(new KeyboardEvent('keydown', { key: '0', code: 'Digit0', bubbles: true }));
    """)
    typed_grab_x = await eval_js("App.state.components.find(comp => comp.id === 'horiz-stab').x")
    print(f"Typed 20 in X-constrained Grab: dx={typed_grab_x - x_before_8c:.2f}")
    assert abs((typed_grab_x - x_before_8c) - 20) < 1e-2, f"Typing 20 should set dx=20, got {typed_grab_x - x_before_8c}"
    # Confirm with Enter
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
    """)
    x_after_8c = await eval_js("App.state.components.find(comp => comp.id === 'horiz-stab').x")
    assert abs(x_after_8c - typed_grab_x) < 1e-2, "Position should persist after Enter"

    # 9. Test 'G' Grab mode cancellation with Escape and Right-Click
    print("9. Testing 'G' Grab mode cancellation with Escape and Right-Click...")
    # 9A: Escape cancel
    saved_x = await eval_js("App.state.components.find(comp => comp.id === 'horiz-stab').x")
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'g', code: 'KeyG', bubbles: true }));
        updateModalTransformFromMouse({ u: App.ui.modalTransform.mouseStartCAD.u + 20, v: App.ui.modalTransform.mouseStartCAD.v });
    """)
    temp_x = await eval_js("App.state.components.find(comp => comp.id === 'horiz-stab').x")
    assert abs(temp_x - (saved_x + 20)) < 1e-2, "Temp position should be modified during grab"
    # Press Escape
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true }));
    """)
    restored_x = await eval_js("App.state.components.find(comp => comp.id === 'horiz-stab').x")
    print(f"Escape cancel: restored x={restored_x:.2f} (original: {saved_x:.2f})")
    assert abs(restored_x - saved_x) < 1e-2, "Position should revert to original on Escape"

    # 9B: Right-click cancel
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'g', code: 'KeyG', bubbles: true }));
        updateModalTransformFromMouse({ u: App.ui.modalTransform.mouseStartCAD.u + 30, v: App.ui.modalTransform.mouseStartCAD.v });
        // Right-click mousedown
        window.dispatchEvent(new MouseEvent('mousedown', { button: 2, bubbles: true }));
    """)
    restored_rclick_x = await eval_js("App.state.components.find(comp => comp.id === 'horiz-stab').x")
    print(f"Right-click cancel: restored x={restored_rclick_x:.2f} (original: {saved_x:.2f})")
    assert abs(restored_rclick_x - saved_x) < 1e-2, "Position should revert to original on Right-Click"

    # 10. Test 'R' Rotate mode with axis constraint, Enter confirm, and Escape cancel
    print("10. Testing 'R' Rotate mode with axis constraint, Enter confirm, and Escape cancel...")
    init_rot_z = await eval_js("App.state.components.find(comp => comp.id === 'horiz-stab').rotZ || 0")
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'r', code: 'KeyR', bubbles: true }));
    """)
    mt_mode_r = await eval_js("App.ui.modalTransform?.mode")
    assert mt_mode_r == 'rotate', f"Modal transform should be 'rotate', got {mt_mode_r}"

    # Press 'z'
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'z', code: 'KeyZ', bubbles: true }));
    """)
    axis_r = await eval_js("App.ui.modalTransform?.axis")
    assert axis_r == 'z', f"Rotation axis should be 'z', got {axis_r}"

    # Move mouse around center to rotate 45 deg
    await eval_js("""
        (() => {
            const mt = App.ui.modalTransform;
            const newAngle = mt.startAngle + (Math.PI / 4); // +45 deg
            const cadPt = {
                u: mt.center2D.u + 50 * Math.cos(newAngle),
                v: mt.center2D.v + 50 * Math.sin(newAngle)
            };
            updateModalTransformFromMouse(cadPt);
        })()
    """)
    cur_rot_z = await eval_js("App.state.components.find(comp => comp.id === 'horiz-stab').rotZ")
    print(f"Rotated Z: {init_rot_z} -> {cur_rot_z:.1f} deg")
    assert abs((cur_rot_z - init_rot_z) - 45) < 1.0, f"rotZ should have changed by ~45 deg, got {cur_rot_z - init_rot_z}"

    # Verify dotted circle and text 'ROT' are removed, and badge only displays degrees
    has_circle = await eval_js("!!document.querySelector('#modal-transform-layer circle')")
    assert not has_circle, "Dotted circle must be removed during rotation"
    guideline_text = await eval_js("document.querySelector('#modal-transform-layer')?.textContent || ''")
    assert "ROT" not in guideline_text, "ROT text must be removed from modal transform guidelines"
    badge_text = await eval_js("document.getElementById('cursor-transform-badge')?.innerText || ''")
    assert "rot" not in badge_text.lower(), f"Cursor badge must not have text 'rot', got '{badge_text}'"
    assert "45.0°" in badge_text, f"Cursor badge should display degrees '45.0°', got '{badge_text}'"

    # Press Enter
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
    """)
    final_rot_z = await eval_js("App.state.components.find(comp => comp.id === 'horiz-stab').rotZ")
    assert abs(final_rot_z - cur_rot_z) < 1e-2, "Rotation should persist after Enter"

    # 10b. Test directional numeric rotation: rotate negative with mouse, type 30, press Enter -> rotates -30 deg
    print("10b. Testing directional numeric rotation in negative direction...")
    init_rot_before_neg = final_rot_z
    await eval_js("""
        (() => {
            window.dispatchEvent(new KeyboardEvent('keydown', { key: 'r', code: 'KeyR', bubbles: true }));
            const mt = App.ui.modalTransform;
            const negAngle = mt.startAngle - (Math.PI / 12); // -15 deg
            updateModalTransformFromMouse({
                u: mt.center2D.u + 50 * Math.cos(negAngle),
                v: mt.center2D.v + 50 * Math.sin(negAngle)
            });
            // Type '3' then '0'
            window.dispatchEvent(new KeyboardEvent('keydown', { key: '3', code: 'Digit3', bubbles: true }));
            window.dispatchEvent(new KeyboardEvent('keydown', { key: '0', code: 'Digit0', bubbles: true }));
        })()
    """)
    neg_badge = await eval_js("document.getElementById('cursor-transform-badge')?.innerText || ''")
    print(f"Typed badge during negative rotation: '{neg_badge}'")
    assert "-30°" in neg_badge, f"Badge should show '-30°' when typing 30 in negative direction, got '{neg_badge}'"

    # Confirm with Enter
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
    """)
    rot_after_typed_neg = await eval_js("App.state.components.find(comp => comp.id === 'horiz-stab').rotZ")
    print(f"Rotated negative via typing: {init_rot_before_neg} -> {rot_after_typed_neg:.1f}")
    assert abs((rot_after_typed_neg - init_rot_before_neg) - (-30)) < 1.0, f"rotZ should have changed by -30 deg, got {rot_after_typed_neg - init_rot_before_neg}"

    # Test Rotate Escape cancel
    await eval_js("""
        (() => {
            window.dispatchEvent(new KeyboardEvent('keydown', { key: 'r', code: 'KeyR', bubbles: true }));
            const mt = App.ui.modalTransform;
            const newAngle = mt.startAngle + (Math.PI / 2);
            updateModalTransformFromMouse({
                u: mt.center2D.u + 50 * Math.cos(newAngle),
                v: mt.center2D.v + 50 * Math.sin(newAngle)
            });
            window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true }));
        })()
    """)
    reverted_rot_z = await eval_js("App.state.components.find(comp => comp.id === 'horiz-stab').rotZ")
    print(f"Rotate Escape: restored rotZ={reverted_rot_z:.1f} (expected: {rot_after_typed_neg:.1f})")
    assert abs(reverted_rot_z - rot_after_typed_neg) < 1e-2, "Rotation should revert to original on Escape"

    # 11. Test Left-click confirms modal transform
    print("11. Testing Left-click confirms modal transform...")
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'g', code: 'KeyG', bubbles: true }));
        window.dispatchEvent(new MouseEvent('mousedown', { button: 0, bubbles: true }));
    """)
    mt_after_lclick = await eval_js("App.ui.modalTransform")
    assert mt_after_lclick is None, "Modal transform should confirm and clear on Left-Click"

    # 12. Test Shift+A shortcut adds part directly (no prompt modal) and dropdown shape switching
    print("12. Testing 'Shift+A' shortcut adds part directly and dropdown shape switching...")
    modal_el = await eval_js("document.getElementById('add-part-modal')")
    assert modal_el is None, "add-part-modal element should be removed from DOM"

    comp_count_before_shifta = await eval_js("App.state.components.length")

    # Dispatch Shift+A
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'A', code: 'KeyA', shiftKey: true, bubbles: true }));
    """)
    comp_count_after_shifta = await eval_js("App.state.components.length")
    print(f"Components count after Shift+A: {comp_count_before_shifta} -> {comp_count_after_shifta}")
    assert comp_count_after_shifta == comp_count_before_shifta + 1, "Shift+A should add a component directly"

    new_part = await eval_js("App.state.components.find(c => c.id === App.state.selectedComponentId)")
    new_part_id = new_part.get('id')
    assert new_part.get('shape') == 'box', f"Newly added part should default to 'box', got {new_part.get('shape')}"

    # Test changing to cylinder with existing dropdown in properties panel
    print("Testing changing newly created part to cylinder via properties panel dropdown...")
    shape_dropdown_exists = await eval_js("!!document.getElementById('prop-shape')")
    assert shape_dropdown_exists, "prop-shape dropdown should exist in properties panel"

    # Select cylinder in dropdown and trigger change
    await eval_js("""
        const shapeSelect = document.getElementById('prop-shape');
        shapeSelect.value = 'cylinder';
        shapeSelect.dispatchEvent(new Event('change'));
    """)
    updated_part = await eval_js(f"App.state.components.find(c => c.id === '{new_part_id}')")
    assert updated_part.get('shape') == 'cylinder', f"Part shape should be updated to 'cylinder', got {updated_part.get('shape')}"

    cyl_axis_display = await eval_js("document.getElementById('prop-cylinder-axis')?.style.display")
    assert cyl_axis_display != 'none', "prop-cylinder-axis dropdown should become visible when shape is cylinder"

    cyl_id = new_part_id

    # 13. Test Cylinder Inspector Dimension Labels & Axis Switching
    print("13. Testing Cylinder Inspector dimension labels & axis switching...")
    lbl_x = await eval_js("document.getElementById('lbl-prop-sx')?.textContent")
    lbl_y = await eval_js("document.getElementById('lbl-prop-sy')?.textContent")
    lbl_z = await eval_js("document.getElementById('lbl-prop-sz')?.textContent")
    print(f"Labels for axis 'y': X='{lbl_x}', Y='{lbl_y}', Z='{lbl_z}'")
    assert lbl_x == 'Dia (X)', f"Expected 'Dia (X)', got '{lbl_x}'"
    assert lbl_y == 'Thick (Y)', f"Expected 'Thick (Y)', got '{lbl_y}'"
    assert lbl_z == 'Dia (Z)', f"Expected 'Dia (Z)', got '{lbl_z}'"

    # Switch cylinderAxis to 'x' (pod)
    await eval_js("updateComponentProperty('cylinderAxis', 'x'); renderInspector();")
    lbl_x_after = await eval_js("document.getElementById('lbl-prop-sx')?.textContent")
    lbl_y_after = await eval_js("document.getElementById('lbl-prop-sy')?.textContent")
    lbl_z_after = await eval_js("document.getElementById('lbl-prop-sz')?.textContent")
    print(f"Labels for axis 'x': X='{lbl_x_after}', Y='{lbl_y_after}', Z='{lbl_z_after}'")
    assert lbl_x_after == 'Length (X)', f"Expected 'Length (X)', got '{lbl_x_after}'"
    assert lbl_y_after == 'Dia (Y)', f"Expected 'Dia (Y)', got '{lbl_y_after}'"
    assert lbl_z_after == 'Dia (Z)', f"Expected 'Dia (Z)', got '{lbl_z_after}'"

    # Switch cylinderAxis to 'z' (strut)
    await eval_js("updateComponentProperty('cylinderAxis', 'z'); renderInspector();")
    lbl_x_z = await eval_js("document.getElementById('lbl-prop-sx')?.textContent")
    lbl_y_z = await eval_js("document.getElementById('lbl-prop-sy')?.textContent")
    lbl_z_z = await eval_js("document.getElementById('lbl-prop-sz')?.textContent")
    print(f"Labels for axis 'z': X='{lbl_x_z}', Y='{lbl_y_z}', Z='{lbl_z_z}'")
    assert lbl_x_z == 'Dia (X)', f"Expected 'Dia (X)', got '{lbl_x_z}'"
    assert lbl_y_z == 'Dia (Y)', f"Expected 'Dia (Y)', got '{lbl_y_z}'"
    assert lbl_z_z == 'Height (Z)', f"Expected 'Height (Z)', got '{lbl_z_z}'"

    # Switch shape to 'box'
    await eval_js("updateComponentProperty('shape', 'box'); renderInspector();")
    lbl_box_x = await eval_js("document.getElementById('lbl-prop-sx')?.textContent")
    lbl_box_y = await eval_js("document.getElementById('lbl-prop-sy')?.textContent")
    lbl_box_z = await eval_js("document.getElementById('lbl-prop-sz')?.textContent")
    print(f"Labels for shape 'box': X='{lbl_box_x}', Y='{lbl_box_y}', Z='{lbl_box_z}'")
    assert lbl_box_x == 'Length (X)' and lbl_box_y == 'Width (Y)' and lbl_box_z == 'Height (Z)', "Box labels incorrect"

    # Switch back to cylinder 'y'
    await eval_js("updateComponentProperty('shape', 'cylinder'); updateComponentProperty('cylinderAxis', 'y'); renderInspector();")

    # 14. Test Cylinder Volume & Mass calculation (Solid vs Hollow)
    print("14. Testing Cylinder Volume and Mass calculation...")
    await eval_js("""
        (() => {
            const comp = App.state.components.find(c => c.id === App.state.selectedComponentId);
            comp.sx = 10;
            comp.sy = 2;
            comp.sz = 10;
            comp.isHollow = false;
            comp.rho = 0.5;
            refresh();
        })()
    """)
    vol_solid = await eval_js("""
        (() => {
            const comp = App.state.components.find(c => c.id === App.state.selectedComponentId);
            return getComponentVolumeCm3(comp);
        })()
    """)
    # Volume of solid cylinder: pi/4 * 10 * 2 * 10 = 50 * pi = ~157.0796 cm3
    expected_solid = (3.141592653589793 / 4.0) * 10.0 * 2.0 * 10.0
    print(f"Solid cylinder volume: {vol_solid:.4f} cm3 (expected: {expected_solid:.4f})")
    assert abs(vol_solid - expected_solid) < 1e-2, f"Solid volume mismatch: {vol_solid} vs {expected_solid}"

    # Now make it hollow with wallT = 0.5
    await eval_js("""
        (() => {
            const comp = App.state.components.find(c => c.id === App.state.selectedComponentId);
            comp.isHollow = true;
            comp.wallT = 0.5;
            refresh();
        })()
    """)
    vol_hollow = await eval_js("""
        (() => {
            const comp = App.state.components.find(c => c.id === App.state.selectedComponentId);
            return getComponentVolumeCm3(comp);
        })()
    """)
    # Inner dimensions: sx_in = 10 - 2*0.5 = 9, sy_in = 2 - 2*0.5 = 1, sz_in = 10 - 2*0.5 = 9
    # Inner volume = pi/4 * 9 * 1 * 9 = 20.25 * pi
    # Hollow volume = 50 * pi - 20.25 * pi = 29.75 * pi = ~93.4624 cm3
    expected_hollow = (3.141592653589793 / 4.0) * (10.0 * 2.0 * 10.0 - 9.0 * 1.0 * 9.0)
    print(f"Hollow cylinder volume: {vol_hollow:.4f} cm3 (expected: {expected_hollow:.4f})")
    assert abs(vol_hollow - expected_hollow) < 1e-2, f"Hollow volume mismatch: {vol_hollow} vs {expected_hollow}"

    # 15. Test + Add button directly adds a part without prompt modal
    print("15. Testing + Add button creates part directly without modal...")
    count_before_btn = await eval_js("App.state.components.length")
    await eval_js("document.getElementById('btn-add-comp').click();")
    count_after_btn = await eval_js("App.state.components.length")
    print(f"Components count after +Add button: {count_before_btn} -> {count_after_btn}")
    assert count_after_btn == count_before_btn + 1, "+Add button should add a component directly"
    assert await eval_js("document.getElementById('add-part-modal')") is None, "Modal should not exist"

    # 16. For D01.0: Test 3D WebGL Cylinder Mesh
    if "D01.0" in label:
        print("16. Testing 3D WebGL Cylinder mesh generation...")
        await eval_js("setView('orbit3d');")
        await asyncio.sleep(0.5)
        mesh_vert_count = await eval_js(f"""
            (() => {{
                const entry = App.three.compMeshes.get('{cyl_id}');
                if (!entry || !entry.normal) return 0;
                return entry.normal.geometry.attributes.position.count;
            }})()
        """)
        print(f"3D Cylinder mesh vertex count: {mesh_vert_count}")
        assert mesh_vert_count > 0, "Cylinder component should have a valid 3D mesh in Three.js"
        # Switch back to 2D top view
        await eval_js("setView('top');")

    # 17. Test Delete key with browser confirm popup
    print("17. Testing Delete key with browser confirm popup...")
    # Select horiz-stab
    await eval_js("handleSelectComponent('horiz-stab'); renderShortcutsLegend();")
    legend_has_del = await eval_js("document.getElementById('shortcuts-legend').innerHTML.includes('Delete Part')")
    assert legend_has_del, "Shortcuts legend should mention 'Delete Part' when a part is selected"

    # Set up confirm mock that rejects (returns false)
    await eval_js("""
        window._confirmCalls = [];
        window._confirmResponse = false;
        window.confirm = function(msg) {
            window._confirmCalls.push(msg);
            return window._confirmResponse;
        };
    """)
    comps_before = await eval_js("App.state.components.length")

    # Press Delete key
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Delete', code: 'Delete', bubbles: true }));
    """)
    confirm_calls = await eval_js("window._confirmCalls")
    comps_after_reject = await eval_js("App.state.components.length")
    print(f"Delete rejected: confirm prompt='{confirm_calls}', comps: {comps_before} -> {comps_after_reject}")
    assert len(confirm_calls) == 1, "window.confirm should have been called once"
    assert "Horizontal Stab" in confirm_calls[0], f"Confirm message should mention part name, got {confirm_calls[0]}"
    assert comps_after_reject == comps_before, "Component should NOT be deleted when user says No"

    # Now set confirm response to true (user says Yes)
    await eval_js("""
        window._confirmCalls = [];
        window._confirmResponse = true;
    """)
    # Press Delete key again
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Delete', code: 'Delete', bubbles: true }));
    """)
    confirm_calls_accept = await eval_js("window._confirmCalls")
    comps_after_accept = await eval_js("App.state.components.length")
    has_horiz_stab = await eval_js("!!App.state.components.find(c => c.id === 'horiz-stab')")
    new_selected = await eval_js("App.state.selectedComponentId")
    print(f"Delete accepted: comps: {comps_before} -> {comps_after_accept}, has_horiz_stab: {has_horiz_stab}, new selected: {new_selected}")
    assert len(confirm_calls_accept) == 1, "window.confirm should have been called"
    assert comps_after_accept == comps_before - 1, "Component should be deleted when user says Yes"
    assert not has_horiz_stab, "horiz-stab should no longer exist in components"
    assert new_selected == 'main-wing', "Selection should switch to main-wing"

    # Verify pressing Delete with main-wing selected does NOT trigger confirm
    await eval_js("""
        window._confirmCalls = [];
        handleSelectComponent('main-wing');
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Delete', code: 'Delete', bubbles: true }));
    """)
    wing_calls = await eval_js("window._confirmCalls.length")
    assert wing_calls == 0, "main-wing should not trigger delete confirm"

    # 18. Testing Blender-style Loop Cut modal with mouse wheel scrolling and keyboard adjustments
    print("18. Testing Blender-style Loop Cut modal with mouse wheel and keyboard...")
    # Find or create a component with sections (e.g. fuselage)
    comp_id = await eval_js("""
        (() => {
            const fuse = getAllActiveParts().find(c => c.sections && c.sections.length >= 2 && c.shape !== 'cylinder');
            if (fuse) {
                handleSelectComponent(fuse.id);
                return fuse.id;
            }
            const id = createComponent(null, 'box');
            handleSelectComponent(id);
            return id;
        })()
    """)
    assert comp_id, "Should have a multi-section component selected"

    # Enter isolated view mode
    await eval_js("""
        App.ui.viewParams.isIsolated = true;
        App.ui.viewParams.isolatedSet.clear();
        App.ui.viewParams.isolatedSet.add(App.state.selectedComponentId);
        renderShortcutsLegend();
    """)
    is_iso = await eval_js("App.ui.viewParams.isIsolated")
    assert is_iso, "Should be in isolated mode"

    # Press Ctrl+R to start Loop Cut modal
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'r', code: 'KeyR', ctrlKey: true, bubbles: true }));
    """)
    has_modal = await eval_js("!!App.ui.loopCutModal")
    assert has_modal, "App.ui.loopCutModal should be active after Ctrl+R in isolated mode"
    num_cuts = await eval_js("App.ui.loopCutModal.numCuts")
    assert num_cuts == 1, f"Initial numCuts should be 1, got {num_cuts}"

    # Verify preview layer exists and has elements
    preview_has_children = await eval_js("""
        (() => {
            const layer = document.getElementById('loop-cut-preview-layer');
            return layer && layer.children.length > 0;
        })()
    """)
    assert preview_has_children, "Loop cut preview layer should have preview elements"

    # Verify preview text is only the number of cuts and positioned inside component x range
    preview_badge_text = await eval_js("""
        (() => {
            const layer = document.getElementById('loop-cut-preview-layer');
            const txt = layer.querySelector('text');
            return txt ? txt.textContent : '';
        })()
    """)
    print(f"Loop cut preview badge text: '{preview_badge_text}'")
    assert preview_badge_text == "1", f"Preview badge text should only be the number of cuts '1', got '{preview_badge_text}'"

    # Check loop cut points lie within component's actual X bounds
    preview_pts_valid = await eval_js("""
        (() => {
            const c = getAllActiveParts().find(p => p.id === App.state.selectedComponentId);
            const layer = document.getElementById('loop-cut-preview-layer');
            const poly = layer.querySelector('polygon');
            if (!poly) return false;
            const pts = poly.getAttribute('points').split(' ').map(p => {
                const [u, v] = p.split(',').map(Number);
                return { u, v };
            });
            const minX = Math.min(...pts.map(p => p.u));
            const maxX = Math.max(...pts.map(p => p.u));
            const cMinX = safeParse(c.x);
            const cMaxX = cMinX + safeParse(c.sx);
            // Must lie within [cMinX, cMaxX]
            return minX >= cMinX - 1 && maxX <= cMaxX + 1;
        })()
    """)
    assert preview_pts_valid, "Loop cut preview polygon must be located within the component's coordinates"

    # Check shortcuts legend displays Loop Cut
    legend_text = await eval_js("document.getElementById('shortcuts-legend').innerText")
    assert "LOOP CUT" in legend_text and "1 Cut" in legend_text, "Shortcuts legend should display LOOP CUT and 1 Cut"

    # Test Wheel Scroll Up (deltaY < 0) -> increment to 2 cuts
    await eval_js("""
        window.dispatchEvent(new WheelEvent('wheel', { deltaY: -100, bubbles: true }));
    """)
    num_cuts_after_scroll1 = await eval_js("App.ui.loopCutModal.numCuts")
    print(f"Num cuts after scroll up 1: {num_cuts_after_scroll1}")
    assert num_cuts_after_scroll1 == 2, f"numCuts should be 2 after wheel up, got {num_cuts_after_scroll1}"

    # Scroll up again -> increment to 3 cuts
    await eval_js("""
        window.dispatchEvent(new WheelEvent('wheel', { deltaY: -100, bubbles: true }));
    """)
    num_cuts_after_scroll2 = await eval_js("App.ui.loopCutModal.numCuts")
    print(f"Num cuts after scroll up 2: {num_cuts_after_scroll2}")
    assert num_cuts_after_scroll2 == 3, f"numCuts should be 3 after second wheel up, got {num_cuts_after_scroll2}"

    # Test Wheel Scroll Down (deltaY > 0) -> decrement to 2 cuts
    await eval_js("""
        window.dispatchEvent(new WheelEvent('wheel', { deltaY: 100, bubbles: true }));
    """)
    num_cuts_after_scroll3 = await eval_js("App.ui.loopCutModal.numCuts")
    print(f"Num cuts after scroll down: {num_cuts_after_scroll3}")
    assert num_cuts_after_scroll3 == 2, f"numCuts should be 2 after wheel down, got {num_cuts_after_scroll3}"

    # Test Escape cancels Loop Cut modal without changing sections
    initial_secs_count = await eval_js("""
        (() => {
            const c = getAllActiveParts().find(p => p.id === App.state.selectedComponentId);
            return c.sections.length;
        })()
    """)
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true }));
    """)
    has_modal_after_esc = await eval_js("!!App.ui.loopCutModal")
    assert not has_modal_after_esc, "Loop cut modal should be cancelled on Escape"
    secs_count_after_esc = await eval_js("""
        (() => {
            const c = getAllActiveParts().find(p => p.id === App.state.selectedComponentId);
            return c.sections.length;
        })()
    """)
    assert secs_count_after_esc == initial_secs_count, "Sections count should not change after Escape cancel"

    # Test Right-Click cancels Loop Cut modal
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'r', code: 'KeyR', ctrlKey: true, bubbles: true }));
    """)
    assert await eval_js("!!App.ui.loopCutModal"), "Modal should be active after Ctrl+R"
    await eval_js("""
        window.dispatchEvent(new MouseEvent('mousedown', { button: 2, bubbles: true }));
    """)
    assert not await eval_js("!!App.ui.loopCutModal"), "Modal should be cancelled on Right-Click"

    # Test Keyboard '+' and '-' shortcuts and Confirm with Enter
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'r', code: 'KeyR', ctrlKey: true, bubbles: true }));
    """)
    assert await eval_js("!!App.ui.loopCutModal"), "Modal should be active after Ctrl+R"

    # Press '+' key twice -> cuts should be 3
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: '+', code: 'Equal', bubbles: true }));
        window.dispatchEvent(new KeyboardEvent('keydown', { key: '+', code: 'Equal', bubbles: true }));
    """)
    cuts_via_keys = await eval_js("App.ui.loopCutModal.numCuts")
    print(f"Num cuts via '+' keys: {cuts_via_keys}")
    assert cuts_via_keys == 3, f"numCuts should be 3, got {cuts_via_keys}"

    # Press '-' key once -> cuts should be 2
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: '-', code: 'Minus', bubbles: true }));
    """)
    cuts_via_minus = await eval_js("App.ui.loopCutModal.numCuts")
    print(f"Num cuts via '-' key: {cuts_via_minus}")
    assert cuts_via_minus == 2, f"numCuts should be 2, got {cuts_via_minus}"

    # Confirm with Enter
    await eval_js("""
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
    """)
    has_modal_after_enter = await eval_js("!!App.ui.loopCutModal")
    assert not has_modal_after_enter, "Loop cut modal should be closed after Enter confirm"

    secs_count_after_confirm = await eval_js("""
        (() => {
            const c = getAllActiveParts().find(p => p.id === App.state.selectedComponentId);
            return c.sections.length;
        })()
    """)
    print(f"Sections before: {initial_secs_count}, after 2 cuts: {secs_count_after_confirm}")
    assert secs_count_after_confirm == initial_secs_count + 2, f"Sections count should increase by 2 (from {initial_secs_count} to {initial_secs_count + 2}), got {secs_count_after_confirm}"

    # Clean up isolation mode
    await eval_js("App.ui.viewParams.isIsolated = false; refresh();")

    # 19. Test positive origin axis lines in 2D views (and 3D AxesHelper in D01.0)
    print("19. Testing positive origin axis lines...")
    # Check Top view axes
    await eval_js("setView('top');")
    top_axes = await eval_js("""
        (() => {
            const lines = Array.from(document.querySelectorAll('#axes-layer line'));
            return lines.map(l => ({
                x1: Number(l.getAttribute('x1')),
                y1: Number(l.getAttribute('y1')),
                x2: Number(l.getAttribute('x2')),
                y2: Number(l.getAttribute('y2')),
                stroke: l.getAttribute('stroke'),
                axis: l.getAttribute('data-axis')
            }));
        })()
    """)
    print("Top axes:", top_axes)
    assert len(top_axes) == 2, f"Top view should have 2 axis lines, got {len(top_axes)}"
    top_x = next((a for a in top_axes if a['axis'] == 'x'), None)
    assert top_x and top_x['x1'] == 0 and top_x['y1'] == 0 and top_x['x2'] > 0 and top_x['y2'] == 0 and top_x['stroke'] == '#e74c3c'
    top_y = next((a for a in top_axes if a['axis'] == 'y'), None)
    assert top_y and top_y['x1'] == 0 and top_y['y1'] == 0 and top_y['x2'] == 0 and top_y['y2'] > 0 and top_y['stroke'] == '#2ecc71'

    # Check Side view axes
    await eval_js("setView('side'); renderAircraft();")
    side_axes = await eval_js("""
        (() => {
            const lines = Array.from(document.querySelectorAll('#axes-layer line'));
            return lines.map(l => ({
                x1: Number(l.getAttribute('x1')),
                y1: Number(l.getAttribute('y1')),
                x2: Number(l.getAttribute('x2')),
                y2: Number(l.getAttribute('y2')),
                stroke: l.getAttribute('stroke'),
                axis: l.getAttribute('data-axis')
            }));
        })()
    """)
    print("Side axes:", side_axes)
    assert len(side_axes) == 2, f"Side view should have 2 axis lines, got {len(side_axes)}"
    side_x = next((a for a in side_axes if a['axis'] == 'x'), None)
    assert side_x and side_x['x1'] == 0 and side_x['y1'] == 0 and side_x['x2'] > 0 and side_x['y2'] == 0 and side_x['stroke'] == '#e74c3c'
    side_z = next((a for a in side_axes if a['axis'] == 'z'), None)
    assert side_z and side_z['x1'] == 0 and side_z['y1'] == 0 and side_z['x2'] == 0 and side_z['y2'] < 0 and side_z['stroke'] == '#3498db'

    # Check Front view axes
    await eval_js("setView('front'); renderAircraft();")
    front_axes = await eval_js("""
        (() => {
            const lines = Array.from(document.querySelectorAll('#axes-layer line'));
            return lines.map(l => ({
                x1: Number(l.getAttribute('x1')),
                y1: Number(l.getAttribute('y1')),
                x2: Number(l.getAttribute('x2')),
                y2: Number(l.getAttribute('y2')),
                stroke: l.getAttribute('stroke'),
                axis: l.getAttribute('data-axis')
            }));
        })()
    """)
    assert len(front_axes) == 2, f"Front view should have 2 axis lines, got {len(front_axes)}"
    front_y = next((a for a in front_axes if a['axis'] == 'y'), None)
    assert front_y and front_y['x1'] == 0 and front_y['y1'] == 0 and front_y['x2'] > 0 and front_y['y2'] == 0 and front_y['stroke'] == '#2ecc71'
    front_z = next((a for a in front_axes if a['axis'] == 'z'), None)
    assert front_z and front_z['x1'] == 0 and front_z['y1'] == 0 and front_z['x2'] == 0 and front_z['y2'] < 0 and front_z['stroke'] == '#3498db'

    # Check Three.js 3D Axes in D01.0 if applicable
    is_d_file = await eval_js("!!(window.App && App.three && App.three.axes)")
    if is_d_file:
        axes_opacity = await eval_js("App.three.axes.material.opacity")
        assert abs(axes_opacity - 0.55) < 0.05, f"AxesHelper opacity should be ~0.55, got {axes_opacity}"

    # Reset back to top view
    await eval_js("setView('top'); renderAircraft();")

    print(f"==> ALL TESTS PASSED FOR {label}! <==")

async def main():
    s_path = r"c:\Users\Victor\Documents\Projects\Aircraft-Design-Tool\Aircraft Design Tool S01.9.html"
    d_path = r"c:\Users\Victor\Documents\Projects\Aircraft-Design-Tool\Aircraft Design Tool D01.0.html"

    # Launch Edge headless
    cmd = [
        EDGE_EXE,
        f"--remote-debugging-port={PORT}",
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--user-data-dir=" + os.path.abspath("./.edge_test_shortcuts_profile")
    ]
    proc = subprocess.Popen(cmd)
    try:
        await asyncio.sleep(2)
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
                    if res.get("id") == msg_id:
                        return res

            await send_cmd("Runtime.enable")
            await send_cmd("Page.enable")

            # Run tests on S01.9
            await test_file_shortcuts(ws, s_path, "Version S01.9")

            # Run tests on W1.0
            w_path = r"c:\Users\Victor\Documents\Projects\Aircraft-Design-Tool\Aircraft Design Tool W1.0.html"
            await test_file_shortcuts(ws, w_path, "Version W1.0 (Aero)")

        print("\n==========================================")
        print("SUCCESS: ALL SHORTCUT TESTS PASSED FOR S01.9 & W1.0!")
        print("==========================================")
    finally:
        proc.terminate()
        proc.wait()

if __name__ == "__main__":
    asyncio.run(main())
