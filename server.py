from tornado import websocket, web, ioloop
import json
from _thread import *
from random import shuffle


status_success = {'success': 'true'}
status_fail = {'success': 'false'}


class WebSocketHandler(websocket.WebSocketHandler):
    clients_all = {}
    rooms = []

    def open(self):
        print("ws opened")
        print("new connection from {}".format(self.request.remote_ip))

    def on_message(self, message):
        print(message)
        if message is '123':
            return
        if self.message_handler(message) is not None:  # horrible shit
            game = self.game_check(self)
            game.task_queue.insert(0, (message, self))
        else:
            self.write_message(status_success)

    def on_close(self):
        self.clients_all.pop(self, None)
        print("ws closed")

    def message_handler(self, message):
        message = json.loads(message)
        switcher = {
            'set_name': self.set_name,
            'create_room': self.create_room,
            'join_room': self.join_room
            }
        func = switcher.get(message['action'], lambda x: 1)  # horrible shit pt.2
        return func(message['data'])

    def set_name(self, data):
        name = data['player_name']
        if self not in self.clients_all.keys():
            self.clients_all.update({self: name})
        print(self.clients_all)

    def game_check(self, conn):
        for room in self.rooms:
            if conn in room.clients.keys():
                return room

    def create_room(self, data):
        new_room = GameRoom(**data)
        self.rooms.append(new_room)
        new_room.join_gameroom({self: self.clients_all[self]})
        start_new_thread(self.room_thread, (new_room,))

    def room_thread(self, room):
        while True:
            room.main_loop()

    def join_room(self, data):
        for room in self.rooms:
            if (room.room_name == data['room_name'] and
                room.room_pass == data['room_pass']):

                room.join_gameroom({self: self.clients_all[self]})
                break
            else:
                raise Exception('invalid room name/pass')



class GameRoom:

    def __init__(self, room_name, room_pass, word_count, turn_time):
        self.room_name = room_name
        self.room_pass = room_pass
        self.word_count = word_count  # words per player
        self.turn_time = turn_time
        self.clients = {}
        self.words_all = []
        self.status = 'new game'
        self.task_queue = []
        self.turn_order = []
        self.score = []

    def join_gameroom(self, conn):
        self.clients.update(conn)

    def main_loop(self):
        if self.task_queue:
            task, conn = self.task_queue.pop()
            self.game_msg_handler(task, conn)

    def game_msg_handler(self, msg, conn):
        message = json.loads(msg)
        switch = {
            'word_list': self.get_words,
            'start_game': self.start_game,
            'turn_summary': self.turn_summary
            }
        func = switch.get(message['action'])
        return func(message['data'], conn)

    def start_game(self, data, conn):
        if self.check_game_is_ready:
            shuffle(self.words_all)
            self.turn_order = list(self.clients.keys())
            shuffle(self.turn_order)
            half = len(self.turn_order) // 2
            self.score = [0] * half
            for i, player in enumerate(self.turn_order):

                if i < half:
                    player.write_message({
                                            'action': 'team',
                                            'data':
                                            {
                                                 'team': i,
                                                 'turn_order': self.turn_order
                                            }
                                        }
                                        )
            self.status = 'game in progress'
            self.next_turn()
        else:
            conn.write_message(status_fail)

    def next_player(self):
        while True:
            for connection in self.turn_order:
                yield connection

    def pause_game(self):
        pass

    def high_scores(self):
        teams = {"team{}".format(i): self.score[i] for i in range(len(self.turn_order)//2)}
        msg = {
                "action": "highscores",
                "data": teams
              }
        self._send_all(msg)

    def turn_summary(self, data, conn):
        words = data['words']
        if words:
            self.words_all = [x for x in self.words_all if x not in words]
        points = len(words)
        index = self.turn_order.index(conn)
        if index < len(self.turn_order) // 2:
            self.score[index] += points
        else:
            self.score[index - len(self.turn_order // 2)] += points

        self.next_turn()

    def next_turn(self):
        if self.words_all:
            player = next(self.next_player())
            words = self.words_all[:self.turn_time] if len(self.words_all) > self.turn_time else self.words_all
            player.write_message({
                                    "action": "turn",
                                    "data":
                                    {
                                            "words": words
                                        }
                                 })
        else:
            self.high_scores()

    def check_game_is_ready(self):
        if (len(self.words_all) == self.word_count * len(self.clients.keys())
                and len(self.clients.keys()) % 2 == 0):
            return True

    def get_words(self, data, conn):
        words = data['words']
        if len(words) == self.word_count:
            self.words_all += words
            conn.write_message(status_success)
            print(self.words_all)
        else:
            raise Exception('i will fix this later')  # !1111111

    def _send_all(self, msg):
        [con.write_message(msg) for con in self.clients.keys()]


if __name__ == '__main__':
    app = web.Application([(r'/ws', WebSocketHandler), ])
    app.listen(8888)
    ioloop.IOLoop.instance().start()
