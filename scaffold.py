import os
import re
import argparse
import yaml
from pathlib import Path
from typing import Dict, List

# Regular expression to find file paths, typically bolded in the Markdown output.
# It's designed to be general, matching the text between '**'.
# The script then post-processes this text to handle various formats like:
# - **path/to/file.ext**
# - **filename.ext - A Description**
# - **path/to/file.ext ∙ Version X**
FILE_PATH_PATTERN = re.compile(r"^\*\*([^*]+?)\*\*")

# Regular expression to find a code block start
CODE_BLOCK_PATTERN = re.compile(r"^```(\w*)")

def extract_artifacts_from_markdown(markdown_path: Path, verbose: bool = False) -> Dict[str, str]:
    """
    Parses a Markdown file and extracts file paths and their subsequent code blocks.
    If a file path appears multiple times, the last one found in the file wins.

    Args:
        markdown_path: The path to the input Markdown file.
        verbose: If True, prints detailed debugging information.

    Returns:
        A dictionary where keys are file paths and values are the code content.
    """
    artifacts = {}
    if verbose:
        print("\n[DEBUG] Starting artifact extraction...")
        print(f"[DEBUG] Reading from: {markdown_path}")

    try:
        with open(markdown_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: Markdown file not found at '{markdown_path}'")
        return {}
    except Exception as e:
        print(f"Error reading Markdown file: {e}")
        return {}

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if verbose and line:
            print(f"\n[DEBUG] Processing line {i+1}: '{line}'")

        match = FILE_PATH_PATTERN.match(line)
        
        if match:
            raw_header = match.group(1)
            is_versioned = '∙' in raw_header
            if verbose:
                print(f"[DEBUG]   ✔️ Matched header pattern. Raw content: '{raw_header}'")

            # First, strip any version info (e.g., "∙ Version X")
            header_text = raw_header.split('∙')[0].strip()
            
            # Next, separate the filename from a potential description.
            file_path_str = header_text.split(' - ')[0].strip()
            
            if verbose and file_path_str != raw_header:
                print(f"[DEBUG]   - Cleaned artifact name: '{file_path_str}'")

            # Check to ensure it looks like a real file path.
            is_valid_path = '.' in file_path_str or '/' in file_path_str or '\\' in file_path_str
            if not is_valid_path:
                if verbose:
                    print(f"[DEBUG]   ❌ Skipping '{file_path_str}'. Does not appear to be a file path (missing '.', '/', or '\\').")
                i += 1
                continue
            
            if verbose:
                print(f"[DEBUG]   ➡️ Identified potential artifact: '{file_path_str}'. Now searching for code block.")

            # Look for the start of a code block on the following lines
            j = i + 1
            found_code = False
            while j < len(lines):
                code_line = lines[j].strip()
                code_block_match = CODE_BLOCK_PATTERN.match(code_line)
                if code_block_match:
                    if verbose:
                        print(f"[DEBUG]     ✔️ Found code block start '```{code_block_match.group(1)}' on line {j+1}.")
                    code_content = []
                    k = j + 1
                    while k < len(lines) and not lines[k].strip().startswith('```'):
                        code_content.append(lines[k])
                        k += 1
                    
                    normalized_path = file_path_str.replace('\\', '/')
                    
                    # If artifact already exists, overwrite it (last-one-wins strategy)
                    if normalized_path in artifacts and verbose:
                        print(f"[DEBUG]     ⚠️ Overwriting existing artifact '{normalized_path}' with newer version.")
                    
                    artifacts[normalized_path] = "".join(code_content)
                    print(f"  [+] Found artifact: {normalized_path}{' (Versioned)' if is_versioned else ''}")
                    i = k
                    found_code = True
                    break
                
                if FILE_PATH_PATTERN.match(code_line):
                    if verbose:
                        print(f"[DEBUG]     ❌ Found another file header before a code block. Stopping search for '{file_path_str}'.")
                    break
                j += 1
            
            if not found_code and verbose:
                print(f"[DEBUG]   ❌ Reached end of file without finding a code block for '{file_path_str}'.")
        i += 1
        
    if verbose:
        print(f"\n[DEBUG] Finished artifact extraction. Final count of unique artifacts: {len(artifacts)}.")
    return artifacts

def create_files_from_artifacts(artifacts: Dict[str, str], base_dir: Path):
    """
    Creates files and directories directly from the extracted artifacts.

    Args:
        artifacts: The dictionary of file paths and content.
        base_dir: The root directory to create the files in.
    """
    if not artifacts:
        print("No artifacts found to create.")
        return

    print(f"\nCreating project structure in '{base_dir}'...")
    for file_path_str, content in artifacts.items():
        os_specific_path = os.path.join(*file_path_str.split('/'))
        file_path = base_dir / os_specific_path
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"  [*] Wrote {file_path}")
        except Exception as e:
            print(f"  [!] Error writing file {file_path}: {e}")

def create_project_from_yaml(
    structure: List,
    artifacts: Dict[str, str],
    base_dir: Path,
    current_path: Path,
    empty_files: List[str],
    verbose: bool = False
):
    """
    Recursively creates a project structure based on a YAML definition.
    (Docstring arguments omitted for brevity)
    """
    for item in structure:
        if isinstance(item, dict):
            if 'directory' in item:
                dir_name = item['directory']
                new_path = current_path / dir_name
                print(f"  [*] Creating directory: {new_path.relative_to(base_dir)}")
                new_path.mkdir(exist_ok=True)
                if 'children' in item and item['children']:
                    create_project_from_yaml(item['children'], artifacts, base_dir, new_path, empty_files, verbose)
            
            elif 'file' in item:
                file_name = item['file']
                file_path = current_path / file_name
                relative_path_str = str(file_path.relative_to(base_dir)).replace('\\', '/')
                
                if verbose:
                    print(f"\n[DEBUG] Processing YAML file entry: '{relative_path_str}'")

                content = None
                source = "empty"

                # --- Artifact Lookup Logic ---
                if verbose:
                    print(f"[DEBUG]   - Attempting to match with {len(artifacts)} extracted artifacts.")
                
                # 1. Direct match
                if verbose:
                    print(f"[DEBUG]     - Checking for direct match: '{relative_path_str}'")
                if relative_path_str in artifacts:
                    content = artifacts[relative_path_str]
                    source = "artifact"
                    if verbose:
                        print(f"[DEBUG]       ✔️ SUCCESS: Direct match found.")
                else:
                    if verbose:
                        print(f"[DEBUG]       - FAILED: No direct match. Checking for suffix matches.")
                    # 2. Suffix match
                    for key in artifacts:
                        if verbose:
                            print(f"[DEBUG]         - Comparing YAML path '{relative_path_str}' with artifact key: '{key}'")
                        if relative_path_str.endswith(key):
                            if verbose:
                                print(f"[DEBUG]           - Suffix matches. Checking path boundary...")
                            if relative_path_str == key or relative_path_str.endswith('/' + key):
                                content = artifacts[key]
                                source = f"artifact (matched on '{key}')"
                                if verbose:
                                    print(f"[DEBUG]           ✔️ SUCCESS: Path boundary check passed. Match found.")
                                break 
                            elif verbose:
                                print(f"[DEBUG]           - FAILED: Path boundary check failed.")
                    if not content and verbose:
                        print(f"[DEBUG]     - FAILED: No suffix match found for '{relative_path_str}'.")

                # --- Fallback Content ---
                if content is None:
                    if 'content' in item:
                        content = item['content']
                        source = "YAML content"
                    elif 'template' in item:
                        template_path = base_dir / item['template']
                        try:
                            with open(template_path, 'r', encoding='utf-8') as tf:
                                content = tf.read()
                            source = f"template '{item['template']}'"
                        except FileNotFoundError:
                            print(f"  [!] Template file not found: {template_path}")
                            source = "template (not found)"
                        except Exception as e:
                            print(f"  [!] Error reading template file {template_path}: {e}")
                
                if source == "empty":
                    empty_files.append(relative_path_str)

                try:
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(file_path, 'w', encoding='utf-8') as f:
                        if content:
                            f.write(content)
                    print(f"  [*] Created file: {relative_path_str} (from {source})")
                except Exception as e:
                    print(f"  [!] Error creating file {file_path}: {e}")

def main():
    """Main function to parse arguments and orchestrate file creation."""
    parser = argparse.ArgumentParser(
        description="Extracts code artifacts from a Markdown export and scaffolds a project.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "markdown_file",
        help="Path to the Markdown file to process."
    )
    parser.add_argument(
        "-s", "--structure",
        dest="yaml_file",
        help="Optional path to a YAML file defining the project structure.",
        default=None
    )
    parser.add_argument(
        "-o", "--output",
        dest="output_dir",
        help="Optional output directory name. Defaults to the Markdown file's name without extension.",
        default=None
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable detailed debug logging to trace file matching."
    )
    
    args = parser.parse_args()
    
    markdown_path = Path(args.markdown_file)
    yaml_path = Path(args.yaml_file) if args.yaml_file else None

    print(f"Processing Markdown file: '{markdown_path}'")
    artifacts = extract_artifacts_from_markdown(markdown_path, args.verbose)
    
    if not artifacts and not (yaml_path and yaml_path.exists()):
        print("\nNo artifacts found and no YAML structure provided. Nothing to do.")
        return

    base_dir = Path(args.output_dir) if args.output_dir else Path(markdown_path.stem)
    base_dir.mkdir(exist_ok=True)
    print(f"\nOutput directory: '{base_dir.resolve()}'")

    empty_files = []

    if yaml_path and yaml_path.exists():
        print(f"\nUsing YAML structure from: '{yaml_path}'")
        try:
            with open(yaml_path, 'r', encoding='utf-8') as yf:
                yaml_data = yaml.safe_load(yf)
            
            project_name = yaml_data.get('name')
            project_root = base_dir / project_name if project_name else base_dir
            project_root.mkdir(exist_ok=True)
            
            print(f"Scaffolding project in '{project_root}'...")
            if 'structure' in yaml_data and yaml_data['structure']:
                create_project_from_yaml(yaml_data['structure'], artifacts, project_root, project_root, empty_files, args.verbose)
            else:
                print("  [!] YAML file is missing or has an empty 'structure' key. Cannot build from YAML.")
                if artifacts:
                    print("\nCreating files from found artifacts only.")
                    create_files_from_artifacts(artifacts, project_root)
        except Exception as e:
            print(f"  [!] An unexpected error occurred while processing the YAML file: {e}")
    else:
        print("\nNo YAML structure provided. Creating files from found artifacts only.")
        create_files_from_artifacts(artifacts, base_dir)

    print("\n--- Summary ---")
    if empty_files:
        print("⚠️  The following files were created empty as no matching artifact or content was found:")
        for file_path in sorted(empty_files):
            print(f"  - {file_path}")
    else:
        print("✅ All files defined in the YAML structure were successfully populated from artifacts or other content sources.")

    print("\n✅ Done.")

if __name__ == "__main__":
    main()