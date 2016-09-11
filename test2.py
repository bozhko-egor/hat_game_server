dic1 = {'a': 1,
        'b': 2,
        'c': 3,
        'k': 5000000000}
player = 10000
def abbbc(player, a, b, c):
    print(player + a * b * c)

abbbc(player, **dic1)
