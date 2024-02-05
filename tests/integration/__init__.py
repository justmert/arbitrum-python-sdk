import os
import dotenv

current_file_path = os.path.realpath(__file__)
scripts_directory = os.path.dirname(current_file_path)
src_directory = os.path.dirname(scripts_directory)
project_directory = os.path.dirname(src_directory)

env_path = os.path.join(project_directory, ".env")

dotenv.load_dotenv(dotenv_path=env_path)
