#!/usr/bin/env python3

import os
import pypandoc
import glob
import re

GITHUB_BASE_URL = "https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials"


def fix_relative_links(content, tutorial_name):
    """Fix relative links to point to GitHub repository."""

    # Fix relative file links (e.g., ./scripts/exec.py or scripts/exec.py)
    content = re.sub(
        r"`([^`]+)\s*<\s*\./?([\w/-]+\.\w+)\s*>`__",
        rf"`\1 <{GITHUB_BASE_URL}/{tutorial_name}/\2>`__",
        content,
    )

    # Fix relative directory links (e.g., ./contracts or contracts/)
    content = re.sub(
        r"`([^`]+)\s*<\s*\./?([\w/-]+)/\s*>`__",
        rf"`\1 <{GITHUB_BASE_URL}/{tutorial_name}/\2/>`__",
        content,
    )

    # Fix markdown-style links that were converted to RST
    content = re.sub(
        r"`([^`]+)\s*<(?!http)([\w/-]+(?:\.\w+)?)\s*>`_",
        rf"`\1 <{GITHUB_BASE_URL}/{tutorial_name}/\2>`_",
        content,
    )

    # Fix README.md references to other tutorials
    content = re.sub(
        r"`([^`]+)\s*<\.\./(\w+)/README\.md>`__",
        rf"`\1 <{GITHUB_BASE_URL}/\2/README.md>`__",
        content,
    )

    return content


def remove_duplicate_headers(content):
    """Remove duplicate headers and keep only the first one."""
    # Split content into lines
    lines = content.split("\n")

    # Find the first header (title) and its underline
    title_index = -1
    title_underline_index = -1
    title = ""

    for i, line in enumerate(lines):
        if i < len(lines) - 1 and set(lines[i + 1]) <= {"="}:
            title_index = i
            title_underline_index = i + 1
            title = line
            break

    if title_index == -1:
        return content

    # Remove any subsequent headers that match the title pattern
    new_lines = []
    i = 0
    while i < len(lines):
        if i > title_underline_index and i < len(lines) - 1:
            next_line = lines[i + 1] if i + 1 < len(lines) else ""
            if set(next_line) <= {"="} and len(next_line) > 0:
                # Skip both the header and its underline
                i += 2
                continue
        new_lines.append(lines[i])
        i += 1

    return "\n".join(new_lines)


def add_github_link(content, tutorial_name):
    """Add GitHub repository link after the title."""
    lines = content.split("\n")

    # Find the first header's underline
    title_underline_index = -1
    for i, line in enumerate(lines):
        if set(line) <= {"="} and i > 0:
            title_underline_index = i
            break

    if title_underline_index == -1:
        return content

    # Add GitHub link after the header
    github_link = f"\nCheck out this tutorial on GitHub: `{tutorial_name} <{GITHUB_BASE_URL}/{tutorial_name}>`__\n"

    return "\n".join(lines[: title_underline_index + 1]) + github_link + "\n".join(lines[title_underline_index + 1 :])


def convert_tutorial_readmes():
    """Convert all tutorial README.md files to RST format."""
    # Base paths
    tutorials_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "arbitrum-python-tutorials/tutorials")
    output_dir = os.path.join(os.path.dirname(__file__), "tutorials")

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Get all tutorial directories
    tutorial_dirs = [
        d for d in os.listdir(tutorials_dir) if os.path.isdir(os.path.join(tutorials_dir, d)) and not d.startswith("__")
    ]

    for tutorial in tutorial_dirs:
        readme_path = os.path.join(tutorials_dir, tutorial, "README.md")
        if os.path.exists(readme_path):
            # Convert the file
            output_path = os.path.join(output_dir, f"{tutorial}.rst")
            try:
                output = pypandoc.convert_file(readme_path, "rst", format="md")

                # Add the title if it's not present
                if not output.startswith(tutorial):
                    title = tutorial.replace("_", " ").title()
                    title_decoration = "=" * len(title)
                    output = f"{title}\n{title_decoration}\n\n{output}"

                # Remove duplicate headers
                output = remove_duplicate_headers(output)

                # Add GitHub link
                output = add_github_link(output, tutorial)

                # Fix relative links
                output = fix_relative_links(output, tutorial)

                with open(output_path, "w") as f:
                    f.write(output)
                print(f"Converted {tutorial} README to RST")
            except Exception as e:
                print(f"Error converting {tutorial}: {str(e)}")


if __name__ == "__main__":
    convert_tutorial_readmes()
