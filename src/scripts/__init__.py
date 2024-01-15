import os
from pathlib import Path

__current_file_path = os.path.realpath(__file__)
__scripts_directory = os.path.dirname(__current_file_path)  # Path of src/scripts
__src_directory = os.path.dirname(__scripts_directory)  # Path of src
PROJECT_DIRECTORY = Path(os.path.dirname(__src_directory))  # Root of the project
