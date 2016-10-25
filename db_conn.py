import sqlite3

class GameDataDb:

    def __init__(self):
        self._db_conn = sqlite3.connect('stat_data.db')
        self._db_cursor = self._db_conn.cursor()
        self.game_id = None
        if not self.query("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='Games'").fetchone()[0]:
            self.query('CREATE TABLE Games(ID INTEGER PRIMARY KEY, START_TIME INT, NAME TEXT, WORD_COUNT INT, DURATION INT)')

    def query(self, query, *params):
        return self._db_cursor.execute(query, *params)

    def create_game_table(self, start_time, name, word_count, duration):
        self.game_id = self.query("SELECT COUNT(*) FROM Games").fetchone()[0] + 1
        self.query("INSERT INTO Games(START_TIME, NAME, WORD_COUNT, DURATION) VALUES (?, ?, ?, ?)", (start_time, name, word_count, duration))
        cmd = 'CREATE TABLE GAME_ID_{0}(ID INTEGER PRIMARY KEY, WORD TEXT, DIFFICULTY INT, AUTHOR TEXT)'.format(self.game_id)
        self.query(cmd)

    def close(self):
        self._db_conn.commit()
        self._db_conn.close()

    def insert_word(self, word, difficulty, author):
        self.query("INSERT INTO GAME_ID_{0}(WORD, DIFFICULTY, AUTHOR) VALUES (?, ?, ?)".format(self.game_id), (word, difficulty, author))

    def get_data_by_game_id(self, game_id):
        return self.query("SELECT * FROM GAME_ID_{0}".format(game_id)).fetchall()


if __name__ == '__main__':
    pass
