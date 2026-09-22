import json
import re
import numpy as np

def clean_aerodynamic_data():
    print("Loading heatmap-data.js...")
    with open("heatmap-data.js", "r") as f:
        content = f.read()

    # Extract the raw JSON object from the JS file
    json_match = re.search(r'const HeatmapData\s*=\s*(\{.*?\});', content, re.DOTALL)
    if not json_match:
        print("Error: Could not find 'const HeatmapData = {...};' in file.")
        return

    data = json.loads(json_match.group(1))
    cleaned_data = {}

    # Dimensions: M (0-9), P (0-9), T (6-24)
    for metric, foils in data.items():
        print(f"Processing {metric}...")
        
        # Initialize a 3D grid with NaNs (Not a Number)
        grid = np.full((10, 10, 19), np.nan)
        
        # 1. Populate the grid
        for code, val in foils.items():
            if val is None or val == "N/A" or isinstance(val, str):
                continue
            
            m = int(code[0])
            p = int(code[1])
            t = int(code[2:4])
            
            if 0 <= m <= 9 and 0 <= p <= 9 and 6 <= t <= 24:
                grid[m, p, t-6] = float(val)

        if np.all(np.isnan(grid)):
            cleaned_data[metric] = foils
            continue

        # 2. Despiking (Assassinate the XFOIL anomalies)
        outlier_mask = np.zeros_like(grid, dtype=bool)
        global_range = np.nanmax(grid) - np.nanmin(grid)
        outlier_count = 0
        
        for m in range(10):
            for p in range(10):
                for t in range(19):
                    if np.isnan(grid[m, p, t]):
                        continue
                    
                    # Grab a 3x3x3 box of adjacent airfoils
                    m_min, m_max = max(0, m-1), min(10, m+2)
                    p_min, p_max = max(0, p-1), min(10, p+2)
                    t_min, t_max = max(0, t-1), min(19, t+2)
                    
                    neighborhood = grid[m_min:m_max, p_min:p_max, t_min:t_max].flatten()
                    valid_neighbors = neighborhood[~np.isnan(neighborhood)]
                    
                    if len(valid_neighbors) >= 5:
                        med = np.median(valid_neighbors)
                        dev = abs(grid[m, p, t] - med)
                        
                        # If the pixel deviates by >20% of the local median AND >5% of the overall range
                        if dev > abs(med) * 0.20 and dev > global_range * 0.05:
                            outlier_mask[m, p, t] = True
                            outlier_count += 1
        
        grid[outlier_mask] = np.nan
        print(f"  -> Removed {outlier_count} severe solver spikes.")

        # 3. Laplacian Relaxation (Flood fill the black holes)
        missing_initial = np.isnan(grid).sum()
        for iteration in range(50):
            if not np.isnan(grid).any():
                break
                
            grid_new = np.copy(grid)
            for m in range(10):
                for p in range(10):
                    for t in range(19):
                        if np.isnan(grid[m, p, t]):
                            m_min, m_max = max(0, m-1), min(10, m+2)
                            p_min, p_max = max(0, p-1), min(10, p+2)
                            t_min, t_max = max(0, t-1), min(19, t+2)
                            
                            neighborhood = grid[m_min:m_max, p_min:p_max, t_min:t_max].flatten()
                            valid_neighbors = neighborhood[~np.isnan(neighborhood)]
                            
                            if len(valid_neighbors) > 0:
                                grid_new[m, p, t] = np.mean(valid_neighbors)
            grid = grid_new
            
        missing_final = np.isnan(grid).sum()
        print(f"  -> Interpolated {missing_initial - missing_final} missing data points.")

        # 4. Repackage into a JSON dict
        cleaned_data[metric] = {}
        for m in range(10):
            for p in range(10):
                # Ensure 0 camber always forces 0 position (e.g. 0012)
                eff_p = 0 if m == 0 else p
                for t in range(19):
                    thick = t + 6
                    code = f"{m}{eff_p}{thick:02d}"
                    
                    val = grid[m, eff_p, t]
                    if not np.isnan(val):
                        # Round to 4 decimals to keep the JS file size light
                        cleaned_data[metric][code] = round(float(val), 4)

    # Write the new payload
    print("\nWriting cleaned data to heatmap-data-clean.js...")
    with open("heatmap-data-clean.js", "w") as f:
        f.write("const HeatmapData = ")
        json.dump(cleaned_data, f, separators=(',', ':'))
        f.write(";\n")
    print("Done! The matrix is smooth.")

if __name__ == "__main__":
    clean_aerodynamic_data()