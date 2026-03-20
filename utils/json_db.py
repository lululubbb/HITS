import json, os, threading
from typing import Optional, Dict, Any, List

class JsonCollection:
    def __init__(self, collection_dir: str):
        self._dir = collection_dir
        os.makedirs(self._dir, exist_ok=True)
        self._lock = threading.Lock()

    def find_one(self, filter: Dict[str, Any], projection: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        table_name = filter.get('table_name')
        if not table_name:
            return None
        path = os.path.join(self._dir, f"{table_name}.json")
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            doc = json.load(f)
        if not projection:
            return doc
        if projection.get("_id") == 0:
            doc.pop("_id", None)
        return doc

    def insert_one(self, doc: Dict[str, Any]):
        table_name = doc.get('table_name')
        path = os.path.join(self._dir, f"{table_name}.json")
        with self._lock:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(doc, f, ensure_ascii=False, indent=2)

    def replace_one(self, filter: Dict, doc: Dict[str, Any], upsert: bool = False):
        self.insert_one(doc)

class JsonDatabase:
    def __init__(self, db_root: str, project_name: str):
        self._root = os.path.join(db_root, project_name)
        os.makedirs(self._root, exist_ok=True)

    def get_collection(self, name: str) -> JsonCollection:
        safe = name.replace('/', '%').replace('\\', '%').replace(':', '%')
        return JsonCollection(os.path.join(self._root, safe))

    def __getitem__(self, name: str) -> JsonCollection:
        return self.get_collection(name)

    def list_collection_names(self) -> List[str]:
        if not os.path.isdir(self._root):
            return []
        return [d for d in os.listdir(self._root)
                if os.path.isdir(os.path.join(self._root, d))]
