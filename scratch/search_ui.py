import os, sys

targets = ["Ages 13 or above", "Rooms Required", "FIND ROOMS", "Find Rooms"]

def search_drive(drive_path):
    print(f"Searching {drive_path}...")
    for root, dirs, files in os.walk(drive_path):
        dirs[:] = [d for d in dirs if d not in [
            "venv", "node_modules", ".git", ".gradle", "build", "SteamLibrary", 
            "xamapp", "Program Files", "Program Files (x86)", "Windows", "$Recycle.Bin",
            "AppData", "System Volume Information", ".cache", ".vscode", "games", "Temp"
        ]]
        for f in files:
            if f.endswith((".js", ".jsx", ".ts", ".tsx", ".html", ".dart", ".py", ".vue", ".json")):
                p = os.path.join(root, f)
                try:
                    with open(p, "r", encoding="utf-8", errors="ignore") as fp:
                        content = fp.read()
                        for t in targets:
                            if t in content:
                                print(f"MATCH [{t}]: {p}")
                                sys.stdout.flush()
                                break
                except Exception:
                    pass

if __name__ == "__main__":
    search_drive(r"D:\\")
