import pickle
import os

try:
    results_dir = os.environ['RESULTS_DIR']
    print(f"Results directory is located at: {results_dir}")
except KeyError:
    print("ERROR: RESULTS_DIR environment variable is not set.")

design_name = os.environ['DESIGN_NAME']
gp_out_file = f"{results_dir}/{design_name}_3D.gp.def"

name_die_map = {}
with open(gp_out_file, 'r', encoding='utf-8') as def_file:
        part = False
        indicator = False
        num_bot = 0
        num_upper = 0
        pre_line = ''
        for line in def_file:
            if 'COMPONENTS' in line:
                part = True
            if 'END' in line:
                part = False

            if part:
                if ('PLACED' in line) or ('FIXED' in line):
                    class_name = pre_line.split()[2]
                    cell_name = pre_line.split()[1]
                    if 'bottom' in class_name:
                        num_bot += 1
                        name_die_map[cell_name] = 0
                    elif 'upper' in class_name:
                        num_upper += 1
                        name_die_map[cell_name] = 1
                    
            pre_line = line

with open(f"{results_dir}/name_die_map.pkl", 'wb') as file:
    pickle.dump(name_die_map, file)