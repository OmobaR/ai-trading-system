import os
import shutil
import argparse

base_path = r"C:\Users\olugb\ai-trading-system"

directories = [
    # Source directories (All phases)
    r"src\events", r"src\market_data", r"src\database", r"src\utils", r"src\config",
    r"src\execution", r"src\risk", r"src\strategy", r"src\analysis", r"src\ml",
    r"src\monitoring", r"src\ui",
    
    # Test directories
    r"tests\unit", r"tests\integration", r"tests\performance",
    
    # Docker directories
    r"docker\compose", r"docker\config",
    
    # Documentation directories
    r"docs\api", r"docs\architecture", r"docs\decisions",
    
    # Script directories
    r"scripts\deployment", r"scripts\monitoring", r"scripts\data"
]

def create_directories():
    # Check if base_path exists, create if not
    if not os.path.exists(base_path):
        try:
            os.makedirs(base_path)
            print(f"Created base directory: {base_path}")
        except OSError as e:
            print(f"Error creating base directory: {e}")
            exit(1)

    for directory in directories:
        full_path = os.path.join(base_path, directory)
        try:
            os.makedirs(full_path, exist_ok=True)
            print(f"Created: {full_path}")
        except OSError as e:
            print(f"Error creating {full_path}: {e}")

    print("All directories created successfully!")

def delete_directories():
    for directory in directories:
        full_path = os.path.join(base_path, directory)
        if os.path.exists(full_path) and os.path.isdir(full_path):
            try:
                shutil.rmtree(full_path)
                print(f"Deleted: {full_path}")
            except OSError as e:
                print(f"Error deleting {full_path}: {e}")

    print("All directories deleted successfully!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage project directories")
    parser.add_argument("action", choices=["create", "delete"], help="Action to perform: create or delete directories")
    args = parser.parse_args()

    if args.action == "create":
        create_directories()
    elif args.action == "delete":
        delete_directories()