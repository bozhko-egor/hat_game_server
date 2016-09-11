from tornado import websocket, web, ioloop
import json
from _thread import *
from random import shuffle
from server_replies import *

status_success = {'success': 'true'}
status_fail = {'success': 'false'}


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
        self.check_name(self, message)  # присвоить имя, если нет
        if self.message_handler(message) is not None:  # horrible shit
            game = self.game_check(self)
            game.task_queue.insert(0, (message, self))

    def on_close(self):
        self.clients_all.pop(self, None)
        room = self.game_check(self)
        if room:
            room.clients.pop(self, None)
        print("ws closed({})".format(self.request.remote_ip))

    def message_handler(self, message):
        message = json.loads(message)
        switcher = {
            'enter_room': self.create_or_join_room,
            'get_room_list': self.get_room_list
            }
        func = switcher.get(message['action'], lambda x: 1)  # horrible shit pt.2
        return func(message['data'])

    def game_check(self, conn):
        for room in self.rooms:
            if conn in room.clients.keys():
                return room

    def check_name(self, conn, message):
        if conn not in clients_all.keys():
            clients_all.update({conn: message['player_name']})
            print(clients_all)

    def get_room_list(self, data):
        names = {room.room_name: {"players": [x for x in room.clients.values()],
                                  "status": room.status} for room in self.rooms}
        self.write_message(
                            {
                                "action": "room_list",
                                "data": names
                            }
                           )

    def create_or_join_room(self, data):
        if data['room_name'] not in self.rooms:
            new_room = GameRoom(**data)
            self.rooms.append(new_room)
            new_room.join_gameroom({self: self.clients_all[self]})
            self.write_message(
                createjoin_json(
                        new_room.room_name,
                        new_room.status,
                        new_room.words,
                        new_room.turn_time,
                        list(clients.values())
                     )
                )
            start_new_thread(self.room_thread, (new_room,))
        else:
            for room in self.rooms:
                if room.room_name == data['room_name']:
                    if room.room_pass == data['room_pass']:

                        room.join_gameroom({self: self.clients_all[self]})
                        self.write_message(
                            createjoin_json(
                                room.room_name,
                                room.status,
                                room.words,
                                room.turn_time,
                                list(room.clients.values())
                                )
                            )

                        break
                    else:
                        self.write_message(
                                            {"success": "false",
                                             "description": "Invalid password"})
                else:
                    self.write_message(
                                        {"success": "false",
                                         "description": "Invalid room name"})

    def room_thread(self, room):
        while True:
            room.main_loop()
            if room.status == 'endgame' or not room.clients.keys():
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
        self.player_gen = None
        self.words_pending_form = []

    def join_gameroom(self, conn):
        self.clients.update(conn)
        if len(self.clients.values()) > 1:  # если ты не один в комнате
            self._send_all_but_one(
                                    createjoin_json(
                                        self.room_name,
                                        self.status,
                                        self.words,
                                        self.turn_time,
                                        list(self.clients.values())
                                        ),
                                    conn)

    def main_loop(self):
        if self.task_queue:
            task, conn = self.task_queue.pop()
            self.game_msg_handler(task, conn)

    def game_msg_handler(self, msg, conn):
        message = json.loads(msg)
        switch = {
            'start_game': self.start_word_generation,
            'commit_words': self.get_words,
            'commit_turn': self.turn_summary
            }
        func = switch.get(message['action'])
        return func(message['data'], conn)

    def start_word_generation(self):
        if self.status == 'in_room':
            self.status == 'word_generation'
            self.words_pending_form == list(self.clients.values())
            self._send_all(
                word_generation_json(
                    self.room_name,
                    self.words,
                    self.turn_time,
                    list(self.clients.values()),
                    self.words_pending_form

                ))

    def start_game(self):
        if self.check_game_is_ready:
            self.player_gen = self.next_player()
            shuffle(self.words_all)
            self.turn_order = list(self.clients.keys())
            shuffle(self.turn_order)
            self.score = [0] * len(self.clients.keys())
            self.status = 'hatgame'
            self.next_turn()

    def next_player(self):
        while True:
            for connection in self.turn_order:
                yield connection

    def pause_game(self):
        pass

    def high_scores(self):
        self._send_all({
                    "room_name": self.room_name,
                    "state": "endgame",
                    "data": {
                          "words": self.words,
                          "turn_time": self.turn_time,
                          "players": list(self.clients.values()),
                          "situp": [self.clients[x] for x in self.turn_order],
                          "scores": self.score,
                    }
                    })
        self.status = "endgame"

    def turn_summary(self, data, conn):
        words = data['words']
        if words:
            self.words_all = [x for x in self.words_all if x not in words]
        points = len(words)
        index = self.turn_order.index(conn)
        self.score[index] += points
        self.next_turn()

    def next_turn(self):
        if self.words_all:
            player = next(self.player_gen())
            self._send_all({
                        "room_name": self.room_name,
                        "state": "hatgame",
                        "data": {
                              "words": self.words,
                              "turn_time": self.turn_time,
                              "players": list(self.clients.values()),
                              "turn_player": self.clients[player],
                              "situp": [self.clients[x] for x in self.turn_order],
                              "scores": self.score,
                              "words_remaining": len(self.words_all)
                        }
                        })
            words = self.words_all[:self.turn_time] if len(self.words_all) > self.turn_time else self.words_all
            player.write_message({
                        "room_name": self.room_name,
                        "state": "hatgame",
                        "data": {
                              "words": self.words,
                              "turn_time": self.turn_time,
                              "players": list(self.clients.values()),
                              "turn_player": self.clients[player],
                              "situp": [self.clients[x] for x in self.turn_order],
                              "scores": self.score,
                              "words_remaining": len(self.words_all),
                              "turn_words": words
                        }
                        })
        else:
            self.high_scores()

    def check_game_is_ready(self):
        if (len(self.words_all) == self.word_count * len(self.clients.keys())
                and not len(self.clients.keys()) % 2):
            if self.status == 'word_generation':
                return True

    def get_words(self, data, conn):
        words = data['words']
        if len(words) == self.word_count:
            self.words_all += words
            print(self.words_all)
            self.words_pending_form.remove(self.clients[conn])
            self._send_all(word_generation_json(
                    self.room_name,
                    self.words,
                    self.turn_time,
                    list(self.clients.values()),
                    self.words_pending_form
                    ))
            if not self.words_pending_form:
                self.start_game()
        else:
            raise Exception('i will fix this later')  # !1111111

    def _send_all(self, msg):
        [con.write_message(msg) for con in self.clients.keys()]

    def _send_all_but_one(self, msg, conn):
        [con.write_message(msg) for con in self.clients.keys() if con != conn]

if __name__ == '__main__':
    app = web.Application([(r'/ws', WebSocketHandler), ])
    app.listen(8888)
    ioloop.IOLoop.instance().start()
