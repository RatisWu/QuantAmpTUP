# experiment.py
import tomlkit, tomlkit
import os, sys, shutil
from datetime import datetime
from copy import deepcopy
from LiteInstru.Worker.TWPA_FastTuneUP import TWPA_fastTup
from LiteInstru.TWPA_ana.TWPA_FastTuneUpAna import fastTWPAcali_ana

def pre_process(toml_path:str):
    mission_type:str = ""
    output_folder:str = ''

    # Assuming 'config.toml' is your file
    with open(toml_path, 'r') as file:
        content = file.read()
        sweepLF_config = tomlkit.parse(content)
        mission_type = sweepLF_config['Job_info']['mission']
        sample_name = sweepLF_config['Job_info']['sample']
        output_folder = os.path.join(os.getcwd(),'experiments',f"{sample_name}_job_{datetime.now().strftime('%y%m%d_%H%M%S')}")
        sweepLF_config['Readout']['output'] = output_folder
        x = deepcopy(sweepLF_config)

    with open(toml_path, "w") as f: # Open in text write mode
        f.write(tomlkit.dumps(x))

    return mission_type, output_folder

    

def main():
    # 取得上傳的 TOML 檔路徑
    if len(sys.argv) < 2:
        print("Toml file was not given !")
        sys.exit(1)
    
    toml_path = sys.argv[1]
    print(f"Upload toml file successfully !")

    m_type, output_folder = pre_process(toml_path)

    match m_type.lower():
        case "twpa_tuneup":
            path = TWPA_fastTup(toml_path)
            fastTWPAcali_ana(path)
        case _:
            raise NameError("Unsupported mission type was given !")

    shutil.move(toml_path, os.path.join(output_folder,"request.toml"))

if __name__ == "__main__":
    main()