import os
import re
import json

INPUT_FILE = "airfoil-data-new.js"
OUTPUT_FILE = "heatmap-data.js"

# Basic linear interpolation helper
def interpolate(target_x, x_list, y_list):
    for i in range(len(x_list) - 1):
        x1, x2 = x_list[i], x_list[i+1]
        # Check if target falls between x1 and x2
        if (x1 <= target_x <= x2) or (x2 <= target_x <= x1):
            if x1 == x2: return y_list[i]
            t = (target_x - x1) / (x2 - x1)
            return y_list[i] + t * (y_list[i+1] - y_list[i])
    return None

def process_data():
    if not os.path.exists(INPUT_FILE):
        print(f"ERROR: Cannot find {INPUT_FILE}")
        return

    print("Parsing XFOIL data...")
    with open(INPUT_FILE, 'r') as f:
        content = f.read()

    # Regex to grab each airfoil's data block
    pattern = re.compile(
        r'airfoilPolars\["(\d{4})"\]\s*=\s*\{\s*"alpha":\s*\[(.*?)\],\s*"cl":\s*\[(.*?)\],\s*"cd":\s*\[(.*?)\],\s*"cm":\s*\[(.*?)\],\s*"converged":\s*\[(.*?)\]\s*\};',
        re.DOTALL
    )
    
    matches = pattern.findall(content)
    
    # Initialize the 9 metric dictionaries
    metrics = {
        "max_ld": {},
        "min_sink": {},
        "dash_cd": {},
        "stall_forgiveness": {},
        "cl_max": {},
        "cm0": {},
        "alpha_stall": {},
        "cd_min": {},
        "aerobatic_sym": {}
    }

    processed_count = 0

    for match in matches:
        naca = match[0]
        
        # Convert string arrays to actual lists
        try:
            alpha_raw = [float(x) for x in match[1].split(',')]
            cl_raw = [float(x) for x in match[2].split(',')]
            cd_raw = [float(x) for x in match[3].split(',')]
            cm_raw = [float(x) for x in match[4].split(',')]
            conv_raw = [x.strip().lower() == 'true' for x in match[5].split(',')]
        except ValueError:
            continue

        # Filter out points where XFOIL failed to converge
        alpha, cl, cd, cm = [], [], [], []
        for i in range(len(conv_raw)):
            # Also filter out negative drag anomalies (XFOIL math glitches)
            if conv_raw[i] and cd_raw[i] > 0.001:
                alpha.append(alpha_raw[i])
                cl.append(cl_raw[i])
                cd.append(cd_raw[i])
                cm.append(cm_raw[i])

        if len(alpha) < 5:
            continue # Skip airfoils that heavily failed convergence

        # ---------------------------------------------------
        # METRIC CALCULATIONS
        # ---------------------------------------------------
        
        # 1. Max Lift & Alpha Stall
        cl_max = max(cl)
        idx_stall = cl.index(cl_max)
        alpha_stall = alpha[idx_stall]
        
        # 2. Max L/D
        ld_ratios = [l/d for l, d in zip(cl, cd) if l > 0]
        max_ld = max(ld_ratios) if ld_ratios else 0
        
        # 3. Min Sink (Endurance) = CL^1.5 / CD
        sink_ratios = [(l**1.5)/d for l, d in zip(cl, cd) if l > 0]
        min_sink = max(sink_ratios) if sink_ratios else 0
        
        # 4. Minimum Drag
        cd_min = min(cd)
        
        # 5. Dash Drag (CD at CL = 0.2)
        # We swap X and Y for interpolation: we want CD(y) at a specific CL(x)
        dash_cd = interpolate(0.2, cl, cd)
        
        # 6. Pitching Moment at Alpha = 0
        cm0 = interpolate(0.0, alpha, cm)
        
        # 7. Stall Forgiveness (Drop in CL 2 degrees after stall)
        # Lower number is better (less drop). If it didn't converge past stall, penalize it heavily.
        cl_post_stall = interpolate(alpha_stall + 2.0, alpha, cl)
        if cl_post_stall is None:
            stall_drop = 0.5 # Severe penalty for failing to calculate post-stall
        else:
            stall_drop = cl_max - cl_post_stall
            
        # 8. Aerobatic Symmetry (Diff between max positive and max negative lift)
        cl_min = min(cl)
        aero_sym = abs(abs(cl_max) - abs(cl_min))

        # Store valid metrics
        if dash_cd is not None: metrics["dash_cd"][naca] = round(dash_cd, 4)
        if cm0 is not None: metrics["cm0"][naca] = round(cm0, 4)
        
        metrics["cl_max"][naca] = round(cl_max, 3)
        metrics["alpha_stall"][naca] = round(alpha_stall, 1)
        metrics["max_ld"][naca] = round(max_ld, 2)
        metrics["min_sink"][naca] = round(min_sink, 2)
        metrics["cd_min"][naca] = round(cd_min, 4)
        metrics["stall_forgiveness"][naca] = round(stall_drop, 3)
        metrics["aerobatic_sym"][naca] = round(aero_sym, 3)
        
        processed_count += 1

    print(f"Successfully crunched data for {processed_count} airfoils.")
    print("Writing heatmap matrices...")

    # Write output as a clean JavaScript object
    with open(OUTPUT_FILE, 'w') as f:
        f.write("// Pre-calculated XFOIL Optimization Matrices\n")
        f.write("const HeatmapData = ")
        f.write(json.dumps(metrics, indent=4))
        f.write(";\n")
        
    print(f"Done! {OUTPUT_FILE} generated.")

if __name__ == "__main__":
    process_data()