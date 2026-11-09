import struct
import unittest

from porter import lsfg_reflect as lr


def ins(op, *ops):
    return [((len(ops) + 1) << 16) | op, *ops]


def module(body):
    words = [lr.MAGIC, 0x10300, 0, 100, 0] + [x for i in body for x in i]
    return struct.pack(f"<{len(words)}I", *words)


# ids: 1 void? we only need types. 2 float, 3 uint, 4 image(storage rgba8 2D),
# 5 ptr image, 6 var image, 7 sampler, 8 ptr sampler, 9 var sampler,
# 10 image sampled r32f 2D, 11 ptr, 12 var, 13 vec4, 14 struct, 15 ptr UBO, 16 var,
# 17 const 16 (uint), 18 array of vec4 [16]
def build():
    b = [
        ins(lr.OP_EXECUTION_MODE, 99, lr.EM_LOCAL_SIZE, 8, 4, 1),
        ins(lr.OP_DECORATE, 6, lr.DEC_DESCRIPTOR_SET, 0),
        ins(lr.OP_DECORATE, 6, lr.DEC_BINDING, 1),
        ins(lr.OP_DECORATE, 9, lr.DEC_DESCRIPTOR_SET, 0),
        ins(lr.OP_DECORATE, 9, lr.DEC_BINDING, 3),
        ins(lr.OP_DECORATE, 12, lr.DEC_DESCRIPTOR_SET, 0),
        ins(lr.OP_DECORATE, 12, lr.DEC_BINDING, 2),
        ins(lr.OP_DECORATE, 16, lr.DEC_DESCRIPTOR_SET, 1),
        ins(lr.OP_DECORATE, 16, lr.DEC_BINDING, 0),
        ins(lr.OP_DECORATE, 14, lr.DEC_BLOCK),
        ins(lr.OP_DECORATE, 18, lr.DEC_ARRAY_STRIDE, 16),
        ins(lr.OP_MEMBER_DECORATE, 14, 0, lr.DEC_OFFSET, 0),
        ins(lr.OP_MEMBER_DECORATE, 14, 1, lr.DEC_OFFSET, 256),
        ins(lr.OP_TYPE_FLOAT, 2, 32),
        ins(lr.OP_TYPE_INT, 3, 32, 0),
        ins(lr.OP_TYPE_IMAGE, 4, 2, 1, 0, 0, 0, 2, 4),   # storage, Rgba8
        ins(lr.OP_TYPE_POINTER, 5, 0, 4),
        ins(lr.OP_VARIABLE, 5, 6, 0),
        ins(lr.OP_TYPE_SAMPLER, 7),
        ins(lr.OP_TYPE_POINTER, 8, 0, 7),
        ins(lr.OP_VARIABLE, 8, 9, 0),
        ins(lr.OP_TYPE_IMAGE, 10, 2, 1, 0, 0, 0, 1, 0),  # sampled, Unknown
        ins(lr.OP_TYPE_POINTER, 11, 0, 10),
        ins(lr.OP_VARIABLE, 11, 12, 0),
        ins(lr.OP_TYPE_VECTOR, 13, 2, 4),
        ins(lr.OP_CONSTANT, 3, 17, 16),
        ins(lr.OP_TYPE_ARRAY, 18, 13, 17),
        ins(lr.OP_TYPE_STRUCT, 14, 18, 13),
        ins(lr.OP_TYPE_POINTER, 15, lr.SC_UNIFORM, 14),
        ins(lr.OP_VARIABLE, 15, 16, lr.SC_UNIFORM),
    ]
    return module(b)


class ReflectTests(unittest.TestCase):
    def setUp(self):
        self.r = lr.reflect_bytes(build())
        self.by = {(b["set"], b["binding"]): b for b in self.r["bindings"]}

    def test_local_size(self):
        self.assertEqual(self.r["local_size"], [8, 4, 1])

    def test_storage_image(self):
        b = self.by[(0, 1)]
        self.assertEqual(b["kind"], "storage-image")
        self.assertEqual(b["dim"], "2D")
        self.assertEqual(b["format"], "rgba8")
        self.assertEqual(b["sampled_type"], "f32")

    def test_sampled_image_and_sampler(self):
        self.assertEqual(self.by[(0, 2)]["kind"], "sampled-image")
        self.assertEqual(self.by[(0, 2)]["format"], "Unknown")
        self.assertEqual(self.by[(0, 3)]["kind"], "sampler")

    def test_uniform_buffer(self):
        b = self.by[(1, 0)]
        self.assertEqual(b["kind"], "uniform-buffer")
        self.assertEqual(b["size"], 256 + 16)

    def test_counts(self):
        self.assertEqual(self.r["binding_count"], 4)
        self.assertEqual(self.r["push_constant_size"], 0)

    def test_push_constant(self):
        b = [
            ins(lr.OP_TYPE_FLOAT, 2, 32),
            ins(lr.OP_TYPE_VECTOR, 3, 2, 2),
            ins(lr.OP_TYPE_STRUCT, 4, 3, 2),
            ins(lr.OP_MEMBER_DECORATE, 4, 0, lr.DEC_OFFSET, 0),
            ins(lr.OP_MEMBER_DECORATE, 4, 1, lr.DEC_OFFSET, 8),
            ins(lr.OP_TYPE_POINTER, 5, lr.SC_PUSH_CONSTANT, 4),
            ins(lr.OP_VARIABLE, 5, 6, lr.SC_PUSH_CONSTANT),
        ]
        r = lr.reflect_bytes(module(b))
        self.assertEqual(r["push_constant_size"], 12)
        self.assertEqual(r["binding_count"], 0)

    def test_bad_magic(self):
        with self.assertRaises(ValueError):
            lr.reflect_bytes(b"\0" * 24)


if __name__ == "__main__":
    unittest.main()
