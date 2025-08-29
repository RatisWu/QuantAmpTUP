# experiment.py
import tomlkit, tomlkit
import os, sys, shutil

def get_m_info(toml_path:str):
    mission_type:str = ""
    output_folder:str = ""
    # Assuming 'config.toml' is your file
    with open(toml_path, 'r') as file:
        content = file.read()
        sweepLF_config = tomlkit.parse(content)
        mission_type = sweepLF_config['Job_info']['mission']
        output_folder = sweepLF_config["Readout"]["output"]

    return mission_type, output_folder

    

def main():
    # 取得上傳的 TOML 檔路徑
    if len(sys.argv) < 2:
        print("Toml file was not given !")
        sys.exit(1)
    
    toml_path = sys.argv[1]
    print(f"Upload toml file successfully !")

    m_type, output_folder = get_m_info(toml_path)

    match m_type.lower():
        case "twpa_tuneup":
            from LiteInstru.Worker.TWPA_FastTuneUP import TWPA_fastTup
            from LiteInstru.TWPA_ana.TWPA_FastTuneUpAna import fastTWPAcali_ana
            path = TWPA_fastTup(toml_path)
            fastTWPAcali_ana(path)
        case "twpa_gainsearch":
            from LiteInstru.Worker.TWPA_GainSearch import TWPA_GainMap
            from LiteInstru.TWPA_ana.TWPA_GainSearchAna import TWPA_GainSearch_ana
            path = TWPA_GainMap(toml_path)
            TWPA_GainSearch_ana(path)
        case _:
            raise NameError("Unsupported mission type was given !")

    shutil.copy(toml_path, os.path.join(output_folder,"request.toml"))

if __name__ == "__main__":
    main()