#!/usr/bin/env python3

import os
import sys
import pypandoc
import glob


def convert_md_to_rst(md_file):
    """Convert a markdown file to rst format."""
    rst_file = md_file.replace(".md", ".rst")

    try:
        output = pypandoc.convert_file(md_file, "rst", format="md")
        with open(rst_file, "w") as f:
            f.write(output)
        print(f"Converted {md_file} to {rst_file}")
    except Exception as e:
        print(f"Error converting {md_file}: {str(e)}")


def main():
    """Convert all markdown files in the docs directory to rst."""
    docs_dir = os.path.dirname(os.path.abspath(__file__))
    md_files = glob.glob(os.path.join(docs_dir, "*.md"))

    for md_file in md_files:
        convert_md_to_rst(md_file)


if __name__ == "__main__":
    main()
