import asyncio
import json
import os
import subprocess
import urllib.request
import websockets
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

PORT = 9277
USER_DATA = "C:/tmp/edge_cdp_bugfixes_s01_7"
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
                if "exceptionDetails" in res:
                    print("JS Exception details:", res["exceptionDetails"])
                    raise RuntimeError(f"JS Exception: {res['exceptionDetails']}")
                val = res.get("result", {}).get("value")
                if val is None:
                    print("DEBUG eval_js res:", res)
                return val

            print("=== TEST SUITE: 5 CRITICAL BUG FIXES ===")

            # ----------------------------------------------------
            # BUG 1: Prop Disk & Wing Wake contrast / difference blend mode
            # ----------------------------------------------------
            print("\n[TEST 1] Prop disk and wing wake contrast & difference blend mode...")
            test1 = await eval_js("""
            (() => {
                // Ensure a motor component with prop disk is visible
                let motor = App.state.components.find(c => c.type === 'motor');
                if (!motor) {
                    motor = {
                        id: 'test-motor-1',
                        name: 'Test Motor',
                        type: 'motor',
                        x: 0, y: 0, z: 0, sx: 5, sy: 5, sz: 5,
                        rho: 1.5,
                        showPropDisk: true,
                        propDia: 9
                    };
                    App.state.components.push(motor);
                } else {
                    motor.showPropDisk = true;
                }
                
                // Enable wing wake rendering
                App.ui.showWingWake = true;
                
                // 1. Dark theme check
                document.documentElement.style.setProperty('--bg-black', '#000000');
                currentView = 'side';
                renderAircraft();
                
                const propDisksDark = Array.from(document.querySelectorAll('polygon')).filter(p => 
                    p.getAttribute('style')?.includes('mix-blend-mode: difference') &&
                    p.getAttribute('stroke') === 'rgb(255, 255, 255)'
                );
                
                const wakePolySide = document.querySelector('.wing-wake-visual polygon');
                const wakeLinesSide = Array.from(document.querySelectorAll('.wing-wake-visual line'));
                const wakeLabelSide = document.querySelector('.wing-wake-visual text');
                
                const sideWakeBlend = wakePolySide && wakePolySide.getAttribute('style')?.includes('mix-blend-mode: difference');
                const sideLinesBlend = wakeLinesSide.length > 0 && wakeLinesSide.every(l => l.getAttribute('style')?.includes('mix-blend-mode: difference'));
                const sideLabelBlend = wakeLabelSide && wakeLabelSide.getAttribute('style')?.includes('mix-blend-mode: difference');
                
                // 2. White theme check: prop disks and wake MUST invert and NOT be white
                document.documentElement.style.setProperty('--bg-black', '#ffffff');
                currentView = 'top';
                renderAircraft();
                
                const propDisksWhite = Array.from(document.querySelectorAll('polygon')).filter(p => 
                    p.getAttribute('style')?.includes('mix-blend-mode: difference') &&
                    p.getAttribute('stroke') === 'rgb(0, 0, 0)'
                );
                
                const wakePolyTop = document.querySelector('.wing-wake-visual polygon');
                const wakeLinesTop = Array.from(document.querySelectorAll('.wing-wake-visual line'));
                const wakeLabelTop = document.querySelector('.wing-wake-visual text');
                
                const topWakeBlend = wakePolyTop && wakePolyTop.getAttribute('style')?.includes('mix-blend-mode: difference') && wakePolyTop.getAttribute('stroke') === 'rgb(0, 0, 0)';
                const topLinesBlend = wakeLinesTop.length > 0 && wakeLinesTop.every(l => l.getAttribute('style')?.includes('mix-blend-mode: difference') && l.getAttribute('stroke') === 'rgb(0, 0, 0)');
                const topLabelBlend = wakeLabelTop && wakeLabelTop.getAttribute('style')?.includes('mix-blend-mode: difference') && wakeLabelTop.getAttribute('fill') === 'rgb(0, 0, 0)';
                
                // Reset to dark
                document.documentElement.style.setProperty('--bg-black', '#000000');
                renderAircraft();

                return {
                    propDisksDarkFound: propDisksDark.length > 0,
                    propDisksWhiteFound: propDisksWhite.length > 0,
                    sideWakeBlend: !!sideWakeBlend,
                    sideLinesBlend: !!sideLinesBlend,
                    sideLabelBlend: !!sideLabelBlend,
                    topWakeBlend: !!topWakeBlend,
                    topLinesBlend: !!topLinesBlend,
                    topLabelBlend: !!topLabelBlend
                };
            })()
            """)
            print("  Prop disk and wing wake check:", test1)
            assert test1["propDisksDarkFound"], "On dark background, prop disk should have white stroke"
            assert test1["propDisksWhiteFound"], "On white background, prop disk MUST have black stroke (rgb(0,0,0)), NEVER white!"
            assert test1["sideWakeBlend"], "Side wake polygon should have mix-blend-mode: difference"
            assert test1["sideLinesBlend"], "Side wake streamlines should have mix-blend-mode: difference"
            assert test1["sideLabelBlend"], "Side wake corridor label should have mix-blend-mode: difference"
            assert test1["topWakeBlend"], "Top wake polygon should have mix-blend-mode: difference and rgb(0,0,0) stroke on white bg"
            assert test1["topLinesBlend"], "Top wake streamlines should have mix-blend-mode: difference and rgb(0,0,0) stroke on white bg"
            assert test1["topLabelBlend"], "Top wake label should have mix-blend-mode: difference and rgb(0,0,0) fill on white bg"
            print("  ✓ PASS: Prop disk and wing wake correctly contrast with background (black on white bg, white on dark bg).")

            # ----------------------------------------------------
            # BUG 2: CWL is not always "sport"
            # ----------------------------------------------------
            print("\n[TEST 2] CWL classification reactivity...")
            test2 = await eval_js("""
            (() => {
                const results = [];
                // Test getFlightClassification function directly
                results.push({ val: 3.5, label: getFlightClassification(3.5), expected: "(Glider)" });
                results.push({ val: 5.5, label: getFlightClassification(5.5), expected: "(Trainer)" });
                results.push({ val: 8.0, label: getFlightClassification(8.0), expected: "(Sport)" });
                results.push({ val: 11.5, label: getFlightClassification(11.5), expected: "(Aerobatic)" });
                results.push({ val: 14.0, label: getFlightClassification(14.0), expected: "(Scale Warbird)" });
                
                // Test reactive top bar sync
                // Set lightweight wing / mass to induce Glider or Trainer CWL
                const origSpan = App.state.wingData.b;
                App.state.wingData.b = 300; // Large span -> low CWL
                calculateAircraft();
                
                const topFlightTypeEl = document.getElementById('top-flight-type');
                const topFlightTypePill = document.querySelector('[data-sync="top-flight-type"]');
                const lowCWLText = topFlightTypePill ? topFlightTypePill.textContent : '';
                
                // Set heavy mass -> Warbird CWL
                App.state.wingData.b = 40; // Tiny span -> high CWL
                calculateAircraft();
                const highCWLText = topFlightTypePill ? topFlightTypePill.textContent : '';
                
                // Restore span
                App.state.wingData.b = origSpan;
                calculateAircraft();
                
                return {
                    classificationsMatch: results.every(r => r.label === r.expected),
                    lowCWLText,
                    highCWLText,
                    pillSynced: lowCWLText !== highCWLText && lowCWLText !== "" && highCWLText !== ""
                };
            })()
            """)
            print("  CWL classification check:", test2)
            assert test2["classificationsMatch"], "CWL classifications must match standard ranges"
            assert test2["pillSynced"], f"CWL top pill must update dynamically (got low='{test2['lowCWLText']}', high='{test2['highCWLText']}')"
            assert test2["lowCWLText"] != "(Sport)" or test2["highCWLText"] != "(Sport)", "CWL pill should not be permanently stuck on Sport"
            print("  ✓ PASS: CWL flight classification updates reactively and syncs to top pill.")

            # ----------------------------------------------------
            # BUG 3: Vertical Tail Volume Coefficient ratings
            # ----------------------------------------------------
            print("\n[TEST 3] Vertical tail volume coefficient (Vv) ratings...")
            test3 = await eval_js("""
            (() => {
                // Ensure a vertical stabilizer is present
                let vstab = App.state.components.find(c => getProp(c, 'type') === 'vstab');
                if (!vstab) {
                    vstab = {
                        id: 'test-vstab',
                        name: 'Vertical Stabilizer',
                        type: 'vstab',
                        x: 80, y: 0, z: 5, sx: 15, sy: 1, sz: 12, rho: 0.1
                    };
                    App.state.components.push(vstab);
                }
                
                // Test 3 points for Vv: < 0.022 (Small), 0.022-0.045 (Good), > 0.045 (Oversized)
                // 1. Small Vv
                vstab.sz = 2; // tiny fin
                calculateAircraft();
                const vvSmallGuide = document.getElementById('top-vv-guide')?.innerText;
                const vvSmallColor = document.getElementById('top-vv-guide')?.style.color;
                
                // 2. Good Vv (around 0.033)
                vstab.sz = 16;
                calculateAircraft();
                const vvValGood = parseFloat(document.getElementById('top-vv')?.dataset.raw || 0);
                const vvGoodGuide = document.getElementById('top-vv-guide')?.innerText;
                const vvGoodColor = document.getElementById('top-vv-guide')?.style.color;
                
                // 3. Oversized Vv (> 0.045)
                vstab.sz = 50; // huge fin
                calculateAircraft();
                const vvOversizedGuide = document.getElementById('top-vv-guide')?.innerText;
                const vvOversizedColor = document.getElementById('top-vv-guide')?.style.color;
                
                // Reset fin
                vstab.sz = 12;
                calculateAircraft();
                
                return {
                    small: { guide: vvSmallGuide, color: vvSmallColor },
                    good: { val: vvValGood, guide: vvGoodGuide, color: vvGoodColor },
                    oversized: { guide: vvOversizedGuide, color: vvOversizedColor }
                };
            })()
            """)
            print("  Tail volume coefficient check:", test3)
            assert test3["small"]["guide"] == "(Small)", f"Expected (Small) for tiny fin, got {test3['small']['guide']}"
            assert test3["good"]["guide"] == "(Good)", f"Expected (Good) for normal fin, got {test3['good']['guide']}"
            assert test3["oversized"]["guide"] == "(Oversized)", f"Expected (Oversized) for huge fin, got {test3['oversized']['guide']}"
            print("  ✓ PASS: Vv is correctly rated as (Small) < 0.022, (Good) 0.022-0.045, and (Oversized) > 0.045.")

            # ----------------------------------------------------
            # BUG 4: Mass linking across instances in same config
            # ----------------------------------------------------
            print("\n[TEST 4] Mass linking across instances in same config...")
            test4 = await eval_js("""
            (() => {
                // Find or create parent component
                let parent = App.state.components.find(c => !c.parentId && c.type !== 'wing');
                if (!parent) {
                    parent = {
                        id: 'parent-comp-test',
                        name: 'Parent Pod',
                        type: 'body',
                        x: 10, y: 5, z: 0, sx: 20, sy: 5, sz: 5,
                        rho: 0.15,
                        sections: [{x:0,w:1,h:1,dy:0,dz:0},{x:1,w:1,h:1,dy:0,dz:0}]
                    };
                    App.state.components.push(parent);
                }
                
                // Create an instance of parent
                let instance = App.state.components.find(c => c.parentId === parent.id);
                if (!instance) {
                    instance = {
                        id: 'instance-comp-test',
                        name: 'Parent Pod (Instance)',
                        parentId: parent.id,
                        x: 10, y: -5, z: 0
                    };
                    App.state.components.push(instance);
                }
                
                // 1. Change parent budgetMass explicitly
                parent.budgetMass = 123.45;
                syncInstances();
                calculateAircraft();
                
                const instMassBudget = getEffectiveMassGrams(instance);
                
                // 2. Change parent rho (density) without explicit budgetMass
                delete parent.budgetMass;
                delete instance.budgetMass;
                parent.rho = 0.5;
                syncInstances();
                calculateAircraft();
                
                const parentMassFromRho = getEffectiveMassGrams(parent);
                const instMassFromRho = getEffectiveMassGrams(instance);
                
                // Verify outliner reflects the instance mass visually
                renderComponentList();
                const instOutlinerEl = document.querySelector(`[data-id="${instance.id}"]`);
                const instOutlinerText = instOutlinerEl ? instOutlinerEl.textContent : '';
                
                return {
                    instMassBudget,
                    parentMassFromRho,
                    instMassFromRho,
                    massesMatchBudget: Math.abs(instMassBudget - 123.45) < 0.01,
                    massesMatchRho: Math.abs(parentMassFromRho - instMassFromRho) < 0.001,
                    instOutlinerText
                };
            })()
            """)
            print("  Mass linking check:", test4)
            assert test4["massesMatchBudget"], f"Instance mass should equal parent budgetMass 123.45, got {test4['instMassBudget']}"
            assert test4["massesMatchRho"], f"Instance mass from rho should equal parent mass ({test4['parentMassFromRho']}), got {test4['instMassFromRho']}"
            print("  ✓ PASS: Mass correctly links and syncs across instances in the same config.")

            # ----------------------------------------------------
            # BUG 5: Aerodynamic role and hollow component ungreayed
            # ----------------------------------------------------
            print("\n[TEST 5] Aerodynamic role and hollow component enabled state...")
            test5 = await eval_js("""
            (() => {
                const parent = App.state.components.find(c => !c.parentId && c.type !== 'wing');
                const instance = App.state.components.find(c => c.parentId);
                
                // Select instance first
                if (instance) {
                    App.state.selectedComponentId = instance.id;
                    renderInspector();
                }
                
                const instTypeDisabled = document.getElementById('prop-type')?.disabled;
                const instHollowDisabled = document.getElementById('prop-is-hollow')?.disabled;
                
                // Now select normal parent component
                App.state.selectedComponentId = parent.id;
                renderInspector();
                
                const parentTypeDisabled = document.getElementById('prop-type')?.disabled;
                const parentHollowDisabled = document.getElementById('prop-is-hollow')?.disabled;
                const parentTypeOpacity = document.getElementById('prop-type')?.style.opacity;
                const parentHollowOpacity = document.getElementById('prop-is-hollow')?.style.opacity;
                
                return {
                    instTypeDisabled,
                    instHollowDisabled,
                    parentTypeDisabled,
                    parentHollowDisabled,
                    parentTypeOpacity,
                    parentHollowOpacity
                };
            })()
            """)
            print("  Inspector enabled state check:", test5)
            assert not test5["parentTypeDisabled"], "prop-type must NOT be disabled on standard components"
            assert not test5["parentHollowDisabled"], "prop-is-hollow must NOT be disabled on standard components"
            assert not test5["instTypeDisabled"], "prop-type must NOT be disabled on instances"
            assert not test5["instHollowDisabled"], "prop-is-hollow must NOT be disabled on instances"
            print("  ✓ PASS: Aerodynamic role and hollow component are enabled and not greyed out.")

            print("\n=== ALL 5 BUG FIX VERIFICATIONS PASSED SUCCESSFULLY! ===")

    finally:
        proc.terminate()

if __name__ == "__main__":
    asyncio.run(main())
