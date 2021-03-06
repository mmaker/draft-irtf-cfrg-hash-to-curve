#!/usr/bin/python
# vim: syntax=python

import hashlib
import struct
from random import choice
import sys
if sys.version_info[0] == 3:
    xrange = range
    _as_bytes = lambda x: bytes(x, "utf-8")
    _strxor = lambda str1, str2: bytes( s1 ^ s2 for (s1, s2) in zip(str1, str2) )
else:
    _as_bytes = lambda x: x
    _strxor = lambda str1, str2: ''.join( chr(ord(s1) ^ ord(s2)) for (s1, s2) in zip(str1, str2) )

# defined in RFC 3447, section 4.1
def I2OSP(val, length):
    val = int(val)
    if val < 0 or val >= (1 << (8 * length)):
        raise ValueError("bad I2OSP call: val=%d length=%d" % (val, length))
    ret = [0] * length
    val_ = val
    for idx in reversed(xrange(0, length)):
        ret[idx] = val_ & 0xff
        val_ = val_ >> 8
    ret = struct.pack("=" + "B" * length, *ret)
    assert OS2IP(ret, True) == val
    return ret

# defined in RFC 3447, section 4.2
def OS2IP(octets, skip_assert=False):
    ret = 0
    for octet in struct.unpack("=" + "B" * len(octets), octets):
        ret = ret << 8
        ret += octet
    if not skip_assert:
        assert octets == I2OSP(ret, len(octets))
    return ret

# from draft-irtf-cfrg-hash-to-curve-06
def hash_to_field(msg, count, dst, modulus, degree, blen, expand_fn, hash_fn, security_param):
    len_in_bytes = count * degree * blen
    pseudo_random_octets = expand_fn(msg, dst, len_in_bytes, hash_fn, security_param)
    u_vals = [None] * count
    for i in xrange(0, count):
        e_vals = [None] * degree
        for j in xrange(0, degree):
            elm_offset = blen * (j + i * degree)
            tv = pseudo_random_octets[elm_offset : (elm_offset + blen)]
            e_vals[j] = OS2IP(tv) % modulus
        u_vals[i] = e_vals
    return u_vals

# from draft-irtf-cfrg-hash-to-curve-06
# hash_fn should be, e.g., hashlib.shake_128 (available in Python3 only)
def expand_message_xof(msg, dst, len_in_bytes, hash_fn, _):
    dst = _as_bytes(dst)
    if len(dst) > 255:
        raise ValueError("dst len should be at most 255 bytes")

    # compute prefix-free encoding of DST
    dst_prime = I2OSP(len(dst), 1) + dst
    assert len(dst_prime) == len(dst) + 1

    msg_prime = _as_bytes(msg) + I2OSP(len_in_bytes, 2) + dst_prime
    pseudo_random_octets = hash_fn(msg_prime).digest(len_in_bytes)
    return pseudo_random_octets

# from draft-irtf-cfrg-hash-to-curve-06
# hash_fn should be, e.g., hashlib.sha256
def expand_message_xmd(msg, dst, len_in_bytes, hash_fn, security_param):
    # sanity checks and basic parameters
    b_in_bytes = hash_fn().digest_size
    r_in_bytes = hash_fn().block_size
    assert 8 * b_in_bytes >= 2 * security_param
    dst = _as_bytes(dst)
    if len(dst) > 255:
        raise ValueError("dst len should be at most 255 bytes")

    # compute ell and check that sizes are as we expect
    ell = (len_in_bytes + b_in_bytes - 1) // b_in_bytes
    if ell > 255:
        raise ValueError("bad expand_message_xmd call: ell was %d" % ell)

    # compute prefix-free encoding of DST
    dst_prime = I2OSP(len(dst), 1) + dst
    assert len(dst_prime) == len(dst) + 1

    # padding and length strings
    Z_pad = I2OSP(0, r_in_bytes)
    l_i_b_str = I2OSP(len_in_bytes, 2)

    # compute blocks
    b_vals = [None] * ell
    b_0 = hash_fn(Z_pad + _as_bytes(msg) + l_i_b_str + I2OSP(0, 1) + dst_prime).digest()
    b_vals[0] = hash_fn(b_0 + I2OSP(1, 1) + dst_prime).digest()
    for i in xrange(1, ell):
        b_vals[i] = hash_fn(_strxor(b_0, b_vals[i - 1]) + I2OSP(i + 1, 1) + dst_prime).digest()

    # assemble output
    pseudo_random_octets = (b'').join(b_vals)
    return pseudo_random_octets[0 : len_in_bytes]

def _random_string(strlen):
    return ''.join( chr(choice(range(65, 65 + 26))) for _ in range(0, strlen))

def _test_xmd():
    msg = _random_string(48)
    dst = _random_string(16)
    ress = {}
    for l in range(16, 8192):
        result = expand_message_xmd(msg, dst, l, hashlib.sha512, 256)
        # check for correct length
        assert l == len(result)
        # check for unique outputs
        key = result[:16]
        ress[key] = ress.get(key, 0) + 1
    assert all( x == 1 for x in ress.values() )

def _test_xof():
    msg = _random_string(48)
    dst = _random_string(16)
    ress = {}
    for l in range(16, 8192):
        result = expand_message_xof(msg, dst, l, hashlib.shake_128, 128)
        # check for correct length
        assert l == len(result)
        # check for unique outputs
        key = result[:16]
        ress[key] = ress.get(key, 0) + 1
    assert all( x == 1 for x in ress.values() )

def test_expand():
    _test_xmd()
    if sys.version_info[0] == 3:
        _test_xof()

if __name__ == "__main__":
    test_expand()
