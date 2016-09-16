from tornado import websocket, web, ioloop
import json
from _thread import *
from random import shuffle


class WebSocketHandler(websocket.WebSocketHandler):

    clients_all = {}
    rooms = []

    def check_origin(self, origin):
        return True

    def open(self):
        print("ws opened({})".format(self.request.remote_ip))

    def on_message(self, message):
        if message is None:
            return

        message = json.loads(message)
        if isinstance(message, dict) and 'action' in message.keys():
            self.check_name(self, message)
            if self.message_handler(message):
                game = self.game_check(self)
                game.task_queue.insert(0, (message, self))  # add task to the game's queue
        else:
            self.write_message({"success": "false",
                                "description": "invalid command"})

    def on_close(self):
        self.clients_all.pop(self, None)
        self.leave_game()
        print("ws closed({})".format(self.request.remote_ip))

    def message_handler(self, message):
        switcher = {
            'enter_room': self.create_or_join_room,
            'get_room_list': self.get_room_list,
            'reconnect': self.reconnect,
            'disconnect': self.leave_game
            }
        func = switcher.get(message['action'], lambda x: True)
        return func(message['data'])

    def game_check(self, conn):
        for room in self.rooms:
            if conn in room.clients.keys():
                return room

    def reconnect(self, data):
        room = self.get_game(data['room_name'], data['room_pass'])
        name = self.clients_all[self]
        if room and name in room.clients.keys():
            room.clients.pop(name, None)
            room.join_gameroom({self: self.clients_all[self]})
            room._send_all_but_one({'action': 'player reconnected'}, self)
        else:
            self.write_message({'success': 'false'})

    def get_game(self, name, password):
        for room in self.rooms:
            if room.room_name == name and room.room_pass == password:
                return room
        else:
            return None

    def leave_game(self, *_):
        room = self.game_check(self)
        if room:
            name = room.clients.pop(self, None)
            room.clients[name] = name
            room._send_all_but_one({'action': 'player left the game'}, self)

    def check_name(self, conn, message):
        """Assign a name to the connection if there is none."""
        if conn not in self.clients_all.keys():
            self.clients_all.update({conn: message['player_name']})
            print(self.clients_all)

    def get_room_list(self, data):
        """Respond to the client with dict of rooms and players in it."""
        names = {room.room_name: {"players": [x for x in room.clients.values()],
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
            self.rooms.append(new_room)
            new_room.join_gameroom({self: self.clients_all[self]})
            self.write_message(new_room.get_state())
            start_new_thread(self.room_thread, (new_room,))
        else:
            room = self.get_game(data['room_name'], data['room_pass'])
            if room:
                room.join_gameroom({self: self.clients_all[self]})
                self.write_message(room.get_state())

            else:
                self.write_message({"success": "false",
                                    "description": "invalid name/pass"})

    def room_thread(self, room):
        """Start this thread for each new room."""
        while True:
            room.main_loop()
            if room.status == 'endgame' or not room.check_any_humans_connected():
                break
        self.rooms.remove(room)
        exit()


class GameRoom:

    def __init__(self, room_name, room_pass, words, turn_time):
        self.room_name = room_name
        self.room_pass = room_pass
        self.words = words  # words per player
        self.turn_time = turn_time
        self.clients = {}
        self.words_all = []
        self.status = 'in_room'
        self.task_queue = []
        self.turn_order = []
        self.score = []
        self.situp = []
        self.player_gen = None
        self.words_pending_from = []

    def join_gameroom(self, conn):
        """Assign connection to the gameroom."""
        self.clients.update(conn)
        state = self.get_state()
        if len(self.clients.values()) > 1:  # если ты не один в комнате
            self._send_all_but_one(state, conn)

        #if self.status == ''

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
                  "players": list(self.clients.values()),
                  "situp": self.situp,
                  "scores": self.score,
                  "words_pending_from": self.words_pending_from,
                  "words_remaining": len(self.words_all)
              }}

    def game_msg_handler(self, message, conn):
        switch = {
            'start_game': self.start_word_generation,
            'commit_words': self.get_words,
            'commit_turn': self.turn_summary
            }
        func = switch.get(message['action'])
        return func(message['data'], conn)

    def check_is_everyone_connected(self):
        return all([isinstance(conn, WebSocketHandler) for conn in self.clients.keys()])

    def check_any_humans_connected(self):
        return any([isinstance(conn, WebSocketHandler) for conn in self.clients.keys()])

    def start_word_generation(self, data, conn):
        if self.status == 'in_room' and not len(self.clients) % 2:
            self.status = 'word_generation'

            self.turn_order = list(self.clients.keys())
            shuffle(self.turn_order)

            self.situp = [self.clients[x] for x in self.turn_order]
            self.words_pending_from = list(self.clients.values())

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
                yield connection

    def pause_game(self):
        pass

    def is_connected(self, conn):
        return conn in self.clients.keys()

    def high_scores(self):
        """Start this when words_all count reaches 0.

        After sending this message thread terminates.
        """
        self.status = "endgame"
        state = self.get_state()
        self._send_all(state)

    def turn_summary(self, data, conn):
        words = data['words']
        if words:
            self.words_all = [x for x in self.words_all if x not in words]
        points = len(words)
        index = self.turn_order.index(conn)
        self.score[index] += points
        self.next_turn()

    def next_turn(self):
        """Send current game state to everyone but player whos turn is right now.

        Send updated version with words him instead.
        """
        if self.words_all:
            player = next(self.player_gen)

            state = self.get_state()
            self._send_all_but_one(state, player)

            shuffle(self.words_all)
            words = self.words_all[:self.turn_time] if len(self.words_all) > self.turn_time else self.words_all
            state['data'].update({"turn_words": words})
            player.write_message(state)
        else:
            self.high_scores()

    def check_game_is_ready(self):
        if self.status == 'word_generation' and not self.words_pending_from:
            return True

    def get_words(self, data, conn):
        words = data['words']
        self.words_all += words
        print(self.words_all)
        self.words_pending_from.remove(self.clients[conn])
        state = self.get_state()
        self._send_all(state)
        if not self.words_pending_from:
            self.start_game()

    def _send_all(self, msg):
        [con.write_message(msg) for con in self.clients.keys() if not isinstance(con, str)]

    def _send_all_but_one(self, msg, connection):
        [con.write_message(msg) for con in self.clients.keys() if con != connection and not isinstance(con, str)]


if __name__ == '__main__':
    app = web.Application([(r'/ws', WebSocketHandler), ])
    app.listen(8888)
    ioloop.IOLoop.instance().start()
