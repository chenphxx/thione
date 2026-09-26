"""平台加密容器解密时要用到的 AES-128 解密。

加密容器里只有几十字节的密钥块需要解密, 因此这里用纯 Python 实现解密方向,
不引入加密库或者额外的可执行文件。实现遵循 FIPS-197, 已用标准测试向量校验。
"""

#: AES 的 S 盒, 逆 S 盒由它反推
SBOX = bytes.fromhex(
    "637c777bf26b6fc53001672bfed7ab76"
    "ca82c97dfa5947f0add4a2af9ca472c0"
    "b7fd9326363ff7cc34a5e5f171d83115"
    "04c723c31896059a071280e2eb27b275"
    "09832c1a1b6e5aa0523bd6b329e32f84"
    "53d100ed20fcb15b6acbbe394a4c58cf"
    "d0efaafb434d338545f9027f503c9fa8"
    "51a3408f929d38f5bcb6da2110fff3d2"
    "cd0c13ec5f974417c4a77e3d645d1973"
    "60814fdc222a908846eeb814de5e0bdb"
    "e0323a0a4906245cc2d3ac629195e479"
    "e7c8376d8dd54ea96c56f4ea657aae08"
    "ba78252e1ca6b4c6e8dd741f4bbd8b8a"
    "703eb5664803f60e613557b986c11d9e"
    "e1f8981169d98e949b1e87e9ce5528df"
    "8ca1890dbfe6426841992d0fb054bb16")
INV_SBOX = bytearray(256)
for _index, _value in enumerate(SBOX):
    INV_SBOX[_value] = _index

#: 密钥扩展的轮常量
RCON = (0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36)

#: 分组与密钥的字节数, AES-128 共 10 轮
BLOCK_SIZE = 16
ROUNDS = 10


def decrypt(key, data):
    """按 AES-128-ECB 解密。

    @param key: 16 字节密钥
    @param data: 密文, 长度必须是 16 的整数倍
    @return: 明文
    @throws ValueError: 密钥或者密文长度不合法
    """
    if len(key) != BLOCK_SIZE:
        raise ValueError("AES-128 的密钥必须是 16 字节")
    if len(data) % BLOCK_SIZE:
        raise ValueError("密文长度必须是 16 的整数倍")
    round_keys = _expand_key(key)
    return b"".join(_decrypt_block(round_keys, data[offset:offset + BLOCK_SIZE])
                    for offset in range(0, len(data), BLOCK_SIZE))


def _expand_key(key):
    """把密钥扩展成每一轮要用的轮密钥。

    @param key: 16 字节密钥
    @return: 长度 11 的列表, 每项是 16 字节轮密钥
    """
    words = [list(key[index * 4:index * 4 + 4]) for index in range(4)]
    for index in range(4, (ROUNDS + 1) * 4):
        temp = list(words[index - 1])
        if index % 4 == 0:
            temp = temp[1:] + temp[:1]
            temp = [SBOX[byte] for byte in temp]
            temp[0] ^= RCON[index // 4 - 1]
        words.append([words[index - 4][byte] ^ temp[byte] for byte in range(4)])
    return [bytes(byte for word in words[round_index * 4:round_index * 4 + 4]
                  for byte in word) for round_index in range(ROUNDS + 1)]


def _decrypt_block(round_keys, block):
    """解密一个 16 字节分组。

    @param round_keys: _expand_key() 的结果
    @param block: 16 字节密文分组
    @return: 16 字节明文分组
    """
    state = bytearray(block)
    _add_round_key(state, round_keys[ROUNDS])
    for round_index in range(ROUNDS - 1, 0, -1):
        state = _inv_shift_rows(state)
        state = bytearray(INV_SBOX[byte] for byte in state)
        _add_round_key(state, round_keys[round_index])
        state = _inv_mix_columns(state)
    state = _inv_shift_rows(state)
    state = bytearray(INV_SBOX[byte] for byte in state)
    _add_round_key(state, round_keys[0])
    return bytes(state)


def _add_round_key(state, round_key):
    """把轮密钥异或进状态 (就地修改)。"""
    for index in range(BLOCK_SIZE):
        state[index] ^= round_key[index]


def _inv_shift_rows(state):
    """逆向行移位: 第 n 行循环右移 n 个字节。"""
    shifted = bytearray(BLOCK_SIZE)
    for column in range(4):
        for row in range(4):
            shifted[column * 4 + row] = state[((column - row) % 4) * 4 + row]
    return shifted


def _inv_mix_columns(state):
    """逆向列混淆: 每一列在 GF(2^8) 上乘以固定的多项式。"""
    mixed = bytearray(BLOCK_SIZE)
    for column in range(4):
        column_bytes = state[column * 4:column * 4 + 4]
        for row in range(4):
            mixed[column * 4 + row] = (
                _multiply(column_bytes[0], (14, 9, 13, 11)[row])
                ^ _multiply(column_bytes[1], (11, 14, 9, 13)[row])
                ^ _multiply(column_bytes[2], (13, 11, 14, 9)[row])
                ^ _multiply(column_bytes[3], (9, 13, 11, 14)[row]))
    return mixed


def _multiply(value, factor):
    """GF(2^8) 上的乘法, 既约多项式取 x^8 + x^4 + x^3 + x + 1。"""
    result = 0
    while factor:
        if factor & 1:
            result ^= value
        value <<= 1
        if value & 0x100:
            value ^= 0x1b
        factor >>= 1
    return result & 0xff
