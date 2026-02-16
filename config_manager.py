import json
import os

class ConfigManager:
    def __init__(self, config_path="config.json", ext_path="extensions.json"):
        self.config_path = config_path
        self.ext_path = ext_path
        self.config = self._load_json(config_path)
        self.extensions = self._load_json(ext_path)

    def _load_json(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"Configuration file {path} not found.")
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def get(self, key, default=None):
        return self.config.get(key, default)

    def get_generation_info(self, gen_code):
        gens = self.config.get("generations", {})
        return gens.get(gen_code, gens.get("L5"))  # Default to L5

    def get_root_path(self):
        """Returns the actual path to write/read data based on debug mode."""
        if self.config.get("debug_mode", False):
            path = self.config.get("local_debug_path", "local_tape_storage")
            os.makedirs(path, exist_ok=True)
            return path
        else:
            # Check if drive letter exists
            drive = self.config.get("drive_letter", "T:\\")
            if not os.path.exists(drive):
                # Only raise warning if not in debug, let system handle IO error later
                pass 
            return drive

    def get_file_icon(self, is_dir, filename):
        if is_dir:
            return self.extensions.get("folder", "📁")
        
        _, ext = os.path.splitext(filename.lower())
        icon_map = self.extensions.get("ext", {})
        return icon_map.get(ext, self.extensions.get("default", "📄"))

# Global instance
cfg = ConfigManager()