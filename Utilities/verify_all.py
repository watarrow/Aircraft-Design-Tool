import subprocess
import sys
import os

SCRIPTS = [
    ("Physics & Components Baseline", os.path.join(os.path.dirname(__file__), "test_physics_and_components.py")),
    ("Mass Sets Verification Suite", os.path.join(os.path.dirname(__file__), "test_mass_sets.py")),
    ("Drag & Canvas 60fps Performance", os.path.join(os.path.dirname(__file__), "test_drag_and_performance.py")),
    ("Smart Driving Dimensions", os.path.join(os.path.dirname(__file__), "test_dimensions.py")),
    ("Hold P to Peek Panel", os.path.join(os.path.dirname(__file__), "test_hold_p_peek.py")),
    ("Universal Navigation Controls (MMB Pan, Scroll Zoom, F Reset)", os.path.join(os.path.dirname(__file__), "test_navigation_controls.py")),
    ("Critical Bug Fixes (Contrast/Blend, CWL, Vv, Instance Mass, Inspector)", os.path.join(os.path.dirname(__file__), "test_bugfixes_s01_7.py")),
    ("Export Current View as SVG", os.path.join(os.path.dirname(__file__), "test_export_svg.py"))
]

def main():
    print("=" * 60)
    print("RUNNING ALL AIRCRAFT DESIGN TOOL VERIFICATION SUITES")
    print("=" * 60)
    
    passed = 0
    total = len(SCRIPTS)
    
    for name, script_path in SCRIPTS:
        if not os.path.exists(script_path):
            print(f"[-] SKIPPED: {name} (Script not found at {script_path})")
            continue
            
        print(f"\n[RUNNING] {name}...")
        res = subprocess.run([sys.executable, script_path], capture_output=True, text=True, encoding="utf-8")
        if res.returncode == 0:
            print(f"[PASSED] {name}")
            passed += 1
        else:
            print(f"[FAILED] {name}")
            print("STDOUT:", res.stdout[-800:] if res.stdout else "")
            print("STDERR:", res.stderr[-800:] if res.stderr else "")
            
    print("\n" + "=" * 60)
    print(f"VERIFICATION SUMMARY: {passed}/{total} SUITES PASSED")
    print("=" * 60)
    
    if passed != total:
        sys.exit(1)

if __name__ == "__main__":
    main()
