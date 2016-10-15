from tornado import websocket, web, ioloop
import json
from _thread import *
from random import shuffle
import itertools

class SocketHandler(websocket.WebSocketHandler):

    clients_all = []
    rooms = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = None
        self.room = None
        self.in_room = False
        self.words_guessed = []
        self.words_written = None

    def check_origin(self, origin):
        return True

    def open(self):
        print("ws opened({})".format(self.request.remote_ip))

    def on_message(self, message):
        message = json.loads(message)
        print(message)
        if isinstance(message, dict) and 'action' in message:
            if self.message_handler(message):
                self.room.task_queue.insert(0, (message, self))  # add task to the game's queue
        else:
            self.write_message({"success": "false",
                                "description": "invalid command"})

    def on_close(self):
        self.in_room = False
        self.clients_all.remove(self)
        self.leave_game()
        print("ws closed({}({}))".format(self.request.remote_ip, self.name))

    def message_handler(self, message):
        switcher = {
            'enter_room': self.create_or_join_room,
            'get_room_list': self.get_room_list,
            'reconnect': self.reconnect,
            'disconnect': self.leave_game,
            'set_name': self.set_name
            }
        func = switcher.get(message['action'], lambda x: True)
        return func(message['data'])

    def set_name(self, data):
        if data['player_name'] not in [x.name if isinstance(x, SocketHandler) else x for x in self.clients_all]:
            self.name = data['player_name']
            self.clients_all.append(self)
            print([x.name for x in self.clients_all])
            answer = True
        else:
            answer = False
        data.update({'success': answer,
                    'action': 'set_name'})
        self.write_message(data)

    def reconnect(self, data):
        room = self.get_game(data['room_name'], data['room_pass'])
        if room and self.name in room.clients:
            room.clients.remove(self.name)
            room.join_gameroom(self)
            room._send_all_but_one({'action': 'player reconnected'}, self)
            self.write_message(room.get_state())
        else:
            self.write_message({'success': False})

    def get_game(self, name, password):
        for room in self.rooms:
            if room.room_name == name and room.room_pass == password:
                return room
        else:
            return None

    def leave_game(self, *arg):
        if self.room:
            if arg:
                self.write_message({
                                    "action": "disconnect",
                                    "success": True
                                    })
                room._send_all_but_one({
                                        "player_name": self.name,
                                        "action": "player_left",
                                        }, self)
                self.reset_stat(self)
            else:
                room._send_all_but_one({
                                        "player_name": self.name,
                                        "action": "player_disconnected",
                                        }, self)
            self.in_room = False

    def get_room_list(self, data):
        """Respond to the client with dict of rooms and players in it."""
        names = {room.room_name: {"players": [x.name if isinstance(x, SocketHandler) else x for x in room.clients],
                                  "status": room.status} for room in self.rooms}
        self.write_message({
                                "action": "room_list",
                                "data": names
                           }
                           )

    def create_or_join_room(self, data):
        """Create room with name/pass.

        If there is the room with such combo, join it.
        """
        if data['room_name'] not in [x.room_name for x in self.rooms]:
            new_room = GameRoom(**data)
            self.room = new_room
            self.in_room = True
            self.rooms.append(new_room)
            new_room.join_gameroom(self)
            self.write_message(new_room.get_state())
            start_new_thread(self.room_thread, (new_room,))
        else:
            room = self.get_game(data['room_name'], data['room_pass'])
            if room and room.status == 'in_room':
                room.join_gameroom(self)
                self.room = room
                self.in_room = True
                self.write_message(room.get_state())

            else:
                self.write_message({"success": False,
                                    "description": "invalid name/pass/game has started already"})

    def reset_stat(self, conn):
        conn.in_room = False
        conn.room = None
        conn.words_guessed = []
        conn.words_written = None

    def room_thread(self, room):
        """Start this thread for each new room."""
        while room.status != 'endgame' and room.check_any_humans_connected():
            room.main_loop()
        self.rooms.remove(room)
        for player in room.clients:
            self.reset_stat(player)
        exit()  # shutdown thread


class Word:

    def __init__(self, word, author):
        self.word = word
        self.author = author
        self.time = 0

    def __str__(self):
        return self.word

    def __repr__(self):
        return "Word({}, {})".format(self.word, self.author)


class GameRoom:

    def __init__(self, room_name, room_pass, words, turn_time):
        self.room_name = room_name
        self.room_pass = room_pass
        self.words = words  # words per player
        self.turn_time = turn_time
        self.clients = []
        self.words_all = []
        self.status = 'in_room'
        self.task_queue = []
        self.turn_order = []
        self.score = []
        self.player_gen = None
        self.current_player = None
        self.words_pending_from = []
        self.reroll_gen = None

    def join_gameroom(self, conn):
        """Assign connection to the gameroom."""
        self.clients.append(conn)
        state = self.get_state()
        if len(self.clients) > 1:  # если ты не один в комнате
            self._send_all_but_one(state, conn)

    def main_loop(self):
        if self.task_queue:
            while not self.check_is_everyone_connected():
                pass
            task, conn = self.task_queue.pop()
            self.game_msg_handler(task, conn)

    def get_state(self):
        return {
            "room_name": self.room_name,
            "state": self.status,
            "data": {
                  "words": self.words,
                  "turn_time": self.turn_time,
                  "players": [x.name for x in self.clients],
                  "situp": [x.name for x in self.turn_order],
                  "scores": self.score,
                  "words_pending_from": self.words_pending_from,
                  "words_remaining": len(self.words_all),
                  "turn_player": self.current_player.name if self.current_player else None,
            }}

    def game_msg_handler(self, message, conn):
        switch = {
            'start_game': self.start_word_generation,
            'commit_words': self.get_words,
            'commit_answer': self.commit_answer,
            "reroll_teams": self.reroll_teams
            }
        func = switch.get(message['action'])
        return func(message['data'], conn)

    def check_is_everyone_connected(self):
        return all([conn.in_room for conn in self.clients[:]])

    def check_any_humans_connected(self):
        return any([conn.in_room for conn in self.clients[:]])

    def start_word_generation(self, data, conn):
        if self.status == 'in_room' and not len(self.clients) % 2:
            self.status = 'word_generation'

            self.turn_order = self.clients
            shuffle(self.turn_order)

            self.words_pending_from = [x.name for x in self.turn_order]

            state = self.get_state()
            self._send_all(state)

    def start_game(self):
        if self.check_game_is_ready:
            self.player_gen = self.next_player()
            shuffle(self.words_all)
            self.score = [0] * len(self.clients)
            self.status = 'hatgame'
            self.next_turn()

    def next_player(self):
        """Generator that cycles through list of players."""
        while True:
            for connection in self.turn_order:
                self.current_player = connection
                yield connection

    def is_connected(self, conn):
        return conn in self.clients

    def high_scores(self):
        """Start this when words_all count reaches 0.

        After sending this message thread terminates.
        """
        self.status = "endgame"
        state = self.get_state()
        self._send_all(state)

    def commit_answer(self, data, conn):
        word = self.words_all.pop(0)
        word.time += data['time']
        if not data['last']:
            conn.words_guessed.append(word)
            index = self.turn_order.index(conn)
            self.score[index] += 1
            self._send_all({"action": "word_info",
                            "data": {
                              "word": word.word,
                              "time": word.time,
                              "author": word.author
                            }})
            if not self.words_all:
                self.high_scores()
        else:
            self.words_all.append(word)
            self.next_turn()

    def next_turn(self):
        """Send current game state to everyone but player whos turn is right now.

        Send updated version with words him instead.
        """

        player = next(self.player_gen)

        state = self.get_state()
        self._send_all_but_one(state, player)

        shuffle(self.words_all)
        words = self.words_all[:self.turn_time] if len(self.words_all) > self.turn_time else self.words_all
        state['data'].update({"turn_words": [x.word for x in words]})
        player.write_message(state)

    def check_game_is_ready(self):
        return self.status == 'word_generation' and not self.words_pending_from

    def get_words(self, data, conn):
        conn.words_written = [Word(x, conn.name) for x in data['words']]
        self.words_all += conn.words_written
        self.words_pending_from.remove(conn.name)
        state = self.get_state()
        self._send_all(state)
        if not self.words_pending_from:
            self.start_game()

    def reroll_teams(self, *args):
        if len(self.turn_order) < 4:
            return
        if not self.reroll_gen:
            self.reroll_gen = itertools.permutations(self.turn_order[1:])
            next(self.reroll_gen)
        try:
            self.turn_order = self.turn_order[:1] + list(next(self.reroll_gen))
        except StopIteration:
            self.reroll_gen = None
            self.reroll_teams(*args)
        self._send_all({"action": "reroll_teams",
                       "data": {
                            "new_situp": [x.name for x in self.turn_order]
                        }})

    def _send_all(self, msg):
        [con.write_message(msg) for con in self.clients if con.in_room]

    def _send_all_but_one(self, msg, connection):
        [con.write_message(msg) for con in self.clients if con != connection and con.in_room]

if __name__ == '__main__':
    app = web.Application([(r'/ws', SocketHandler), ])
    app.listen(8888)
    ioloop.IOLoop.instance().start()
