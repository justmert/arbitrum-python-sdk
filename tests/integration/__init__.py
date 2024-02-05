import os
import dotenv

# Construct the path to the .env file
current_file_path = os.path.realpath(__file__)
scripts_directory = os.path.dirname(current_file_path)  # Path of src/scripts
src_directory = os.path.dirname(scripts_directory)  # Path of src
project_directory = os.path.dirname(src_directory)  # Root of the project

env_path = os.path.join(project_directory, ".env")

# Load the .env file
dotenv.load_dotenv(dotenv_path=env_path)
