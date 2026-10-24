class ItemStore:
    def __init__(self, rows):
        self.rows = rows
        self.cache = {}

    def list_items(self, tenant_id):
        key = "items"
        if key not in self.cache:
            self.cache[key] = [row for row in self.rows if row["tenant_id"] == tenant_id]
        return list(self.cache[key])
