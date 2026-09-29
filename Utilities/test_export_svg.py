import asyncio
import json
import os
import subprocess
import urllib.request
import websockets
import sys
import xml.etree.ElementTree as ET

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

PORT = 9289
USER_DATA = "C:/tmp/edge_cdp_export_svg"
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
                    print("JS Exception:", res["exceptionDetails"])
                    raise RuntimeError(f"JS Exception: {res['exceptionDetails']}")
                return res.get("result", {}).get("value")

            print("=== TEST SUITE: EXPORT CURRENT VIEW AS SVG ===")

            # 1. Verify button existence, positioning below Info button, and styling
            print("1. Verifying Export SVG button in Settings DOM...")
            btn_check = await eval_js("""
            (() => {
                const settingsPanel = document.getElementById('settings-menu') || document.querySelector('.settings-panel') || document.getElementById('props-settings');
                const infoBtn = document.getElementById('btn-guide');
                const exportBtn = document.getElementById('btn-export-svg');
                if (!exportBtn) return { error: "Export button #btn-export-svg not found" };
                if (!infoBtn) return { error: "Info button #btn-guide not found" };

                const infoParent = infoBtn.parentElement;
                const exportParent = exportBtn.parentElement;
                const isInsideSettings = infoParent === exportParent;

                // Check that exportBtn is after infoBtn in DOM order
                const siblings = Array.from(infoParent.children);
                const infoIndex = siblings.indexOf(infoBtn);
                const exportIndex = siblings.indexOf(exportBtn);
                const isBelowInfo = exportIndex > infoIndex;

                return {
                    isInsideSettings,
                    isBelowInfo,
                    text: exportBtn.innerText.trim(),
                    className: exportBtn.className,
                    infoStyle: infoBtn.getAttribute('style') || '',
                    exportStyle: exportBtn.getAttribute('style') || ''
                };
            })()
            """)
            print("   Button check result:", btn_check)
            assert "error" not in btn_check, btn_check.get("error")
            assert btn_check["isInsideSettings"], "Export button must be inside settings menu alongside Info button"
            assert btn_check["isBelowInfo"], "Export button must be positioned below the Info button"
            assert btn_check["text"] == "Export current view as SVG", f"Button text must be 'Export current view as SVG', got '{btn_check['text']}'"
            assert "btn-sm" in btn_check["className"], "Export button must have btn-sm class matching Info button style"
            print("   PASS: Button presence, positioning, and styling verified.")

            # 2. Test SVG export for top, side, and front views
            print("\n2. Testing SVG export data generation for top, side, and front views...")
            for view in ['top', 'side', 'front']:
                export_test = await eval_js(f"""
                (() => {{
                    // Intercept download and blob
                    let capturedDownload = null;
                    let exportedSvgText = '';
                    const origClick = HTMLAnchorElement.prototype.click;
                    const origBlob = window.Blob;
                    
                    window.Blob = function(parts, options) {{
                        if (options && options.type && options.type.includes('svg')) {{
                            exportedSvgText = parts.join('');
                        }}
                        return new origBlob(parts, options);
                    }};

                    HTMLAnchorElement.prototype.click = function() {{
                        if (this.download && this.download.endsWith('.svg')) {{
                            capturedDownload = {{
                                filename: this.download,
                                href: this.href
                            }};
                        }}
                    }};

                    // Switch view and render
                    currentView = '{view}';
                    if (App.state) App.state.currentView = '{view}';
                    renderAircraft();

                    // Trigger export
                    exportCurrentViewSVG._busy = false;
                    exportCurrentViewSVG();

                    // Restore
                    HTMLAnchorElement.prototype.click = origClick;
                    window.Blob = origBlob;

                    const parser = new DOMParser();
                    const doc = parser.parseFromString(exportedSvgText, 'image/svg+xml');
                    const allShapes = Array.from(doc.querySelectorAll('path, polygon, polyline, rect, circle, ellipse'));
                    const nonNoneFills = allShapes.filter(el => {{
                        const f = el.getAttribute('fill');
                        return f && f !== 'none';
                    }}).length;

                    return {{
                        capturedDownload,
                        svgContentLength: exportedSvgText.length,
                        hasXmlns: exportedSvgText.includes('xmlns="http://www.w3.org/2000/svg"'),
                        hasViewBox: exportedSvgText.includes('viewBox="'),
                        hasWingLayer: exportedSvgText.includes('id="wing-layer"'),
                        hasComponentsLayer: exportedSvgText.includes('id="components-layer"'),
                        hasCadBgFill: exportedSvgText.includes('id="cad-bg-fill"'),
                        hasBgGridFill: exportedSvgText.includes('id="bg-grid-fill"'),
                        hasFillNoneStyle: exportedSvgText.includes('fill: none !important'),
                        nonNoneFills,
                        totalShapesCount: allShapes.length
                    }};
                }})()
                """)
                download = export_test.get("capturedDownload") or {}
                print(f"   [{view.upper()} VIEW] Export result:")
                print(f"     Filename: {download.get('filename')}")
                print(f"     SVG length: {export_test.get('svgContentLength')}, Shapes count: {export_test.get('totalShapesCount')}")
                print(f"     Pure paths verification: nonNoneFills={export_test.get('nonNoneFills')}, hasCadBgFill={export_test.get('hasCadBgFill')}, hasBgGridFill={export_test.get('hasBgGridFill')}, hasFillNoneStyle={export_test.get('hasFillNoneStyle')}")

                download = export_test.get("capturedDownload")
                assert download is not None, f"Export should trigger a download in {view} view"
                assert f"_{view}_view.svg" in download["filename"], f"Filename should contain _{view}_view.svg, got {download['filename']}"
                assert export_test["hasXmlns"], "Exported SVG must declare XML namespace"
                assert export_test["hasViewBox"], "Exported SVG must have a viewBox attribute"
                assert export_test["hasWingLayer"], "Exported SVG must contain wing layer"
                assert export_test["hasComponentsLayer"], "Exported SVG must contain components layer"
                assert not export_test["hasCadBgFill"], "Exported SVG should not contain background rect #cad-bg-fill"
                assert not export_test["hasBgGridFill"], "Exported SVG should not contain grid fill #bg-grid-fill"
                assert export_test["hasFillNoneStyle"], "Exported SVG should enforce fill: none !important in styles"
                assert export_test["nonNoneFills"] == 0, f"All vector shapes must have fill='none', found {export_test['nonNoneFills']} non-none fills"

            print("   PASS: SVG export in top, side, and front views verified successfully with pure paths (no fills).")

            # 3. Test that clicking #btn-export-svg triggers download exactly ONCE (no double explorer/save dialog)
            print("\n3. Testing single download trigger on #btn-export-svg button click...")
            btn_click_test = await eval_js("""
            (() => {
                let downloadCount = 0;
                const captured = [];
                const origClick = HTMLAnchorElement.prototype.click;
                HTMLAnchorElement.prototype.click = function() {
                    if (this.download && this.download.endsWith('.svg')) {
                        downloadCount++;
                        captured.push(this.download);
                    }
                };

                // Clear any cooldown before clicking
                exportCurrentViewSVG._busy = false;

                const btn = document.getElementById('btn-export-svg');
                if (!btn) return { error: "Button not found" };

                // Click the button as user would
                btn.click();

                // Restore
                HTMLAnchorElement.prototype.click = origClick;

                return {
                    downloadCount,
                    captured
                };
            })()
            """)
            print("   Button click download result:", btn_click_test)
            assert btn_click_test.get("downloadCount") == 1, f"Expected exactly 1 download trigger, got {btn_click_test.get('downloadCount')}!"
            print("   PASS: Clicking export button triggers download exactly once.")

            print("\n=== ALL EXPORT SVG TESTS PASSED! ===")

    finally:
        proc.terminate()

if __name__ == "__main__":
    asyncio.run(main())
