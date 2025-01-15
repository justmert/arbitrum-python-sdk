from pathlib import Path
import os

__current_file_path = os.path.realpath(__file__)
__scripts_directory = os.path.dirname(__current_file_path)
PROJECT_DIRECTORY = Path(os.path.dirname(__scripts_directory))
