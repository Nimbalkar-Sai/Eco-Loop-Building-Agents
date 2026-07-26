from pathlib import Path

# Change this to your installation path
ENERGYPLUS_PATH = Path(r"C:\EnergyPlusV26-1-0")

IDD_FILE = ENERGYPLUS_PATH / "Energy+.idd"

EXAMPLE_DIR = ENERGYPLUS_PATH / "ExampleFiles"

WEATHER_DIR = ENERGYPLUS_PATH / "WeatherData"

WEATHER_FILE = Path("energyplus/weather.epw")

BUILDING_FILE = Path("energyplus/building.idf")