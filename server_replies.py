server_reply_dict = {
                        'create_room': {
                                        "room_name": None,
                                        "state": "in_room",
                                        "data": {
                                              "words": 0,
                                              "turn_time": 0,
                                              "players": []
                                          }
                                        },
                        'start_game': {
                                        "room_name": None,
                                        "state": "word_generation",
                                        "data": {
                                              "words": 0,
                                              "turn_time": 0,
                                              "players": [],
                                              "words_pending_from": []
                                        }
                                        },
                        'words_recieved': {
                                        "room_name": None,
                                        "state": "word_generation",
                                        "data": {
                                              "words": 0,
                                              "turn_time": 0,
                                              "players": [],
                                              "words_pending_from": []
                                        }
                                        },
                        'next_turn': {
                                        "room_name": None,
                                        "state": "hatgame",
                                        "data": {
                                              "words": 0,
                                              "turn_time": 0,
                                              "players": [],
                                              "turn_player": None,
                                              "situp": [],
                                              "scores": [],
                                              "words_remaining": 0
                                        }
                                        },
                        'player_turn': {
                                        "room_name": None,
                                        "state": "hatgame",
                                        "data": {
                                              "words": 0,
                                              "turn_time": 0,
                                              "players": [],
                                              "turn_player": None,
                                              "situp": [],
                                              "scores": [],
                                              "words_remaining": 0,
                                              "turn_words": []
                                        }
                                        },
                        'endgame': {
                                        "room_name": None,
                                        "state": "endgame",
                                        "data": {
                                              "words": 0,
                                              "turn_time": 0,
                                              "players": [],
                                              "situp": [],
                                              "scores": []
                                        }
                                        }}

def createjoin_json(room_name, state, words, turn_time, players):
    msg = {
                    "room_name": room_name,
                    "state": state,
                    "data": {
                          "words": words,
                          "turn_time": turn_time,
                          "players": players
                      }
                    }
    return msg

def word_generation_json(room_name, words, turn_time, players, words_pending_from):
    msg = {
                    "room_name": room_name,
                    "state": "word_generation",
                    "data": {
                          "words": words,
                          "turn_time": 0,
                          "players": players,
                          "words_pending_from": words_pending_from
                    }
                    }
    return msg
