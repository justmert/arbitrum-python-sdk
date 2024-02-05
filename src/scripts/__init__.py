import os
from pathlib import Path

__current_file_path = os.path.realpath(__file__)
__scripts_directory = os.path.dirname(__current_file_path)
__src_directory = os.path.dirname(__scripts_directory)
PROJECT_DIRECTORY = Path(os.path.dirname(__src_directory))
