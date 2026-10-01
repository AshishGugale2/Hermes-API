class BaseRepository:
    def __init__(self, database):
        self.database = database

    def _connect(self):
        return self.database.cursor()
