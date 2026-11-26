package com.suyuan.mobile

import java.math.BigInteger
import java.security.SecureRandom

/**
 * 公司平台国密加密（与 web 前端 frontend/src/auth/SM2.js 同协议：SM2 公钥加密）。
 *
 * 公司账号与密码在发往溯源后端之前先做 SM2 公钥加密：平台公钥编译在包内，只有公司平台
 * 持有私钥，溯源后端与链路上的窃听者都拿不到明文。密文须与 web 前端 sm-crypto doEncrypt
 * 的线上格式逐字节一致：C1(64 字节，无 04 前缀) + C3(32 字节) + C2(与明文等长)，小写 hex。
 * 纯 JDK 实现：曲线 sm2p256v1、SM3、KDF 均按 GB/T 32918.4/.5 与 GB/T 32905。
 */
object CompanyCrypto {
    /** 公司平台 SM2 公钥（65 字节非压缩格式，与 web 前端 SM2.js 内置值一致）。 */
    const val PLATFORM_SM2_PUBLIC_KEY =
        "046644e1cb17328239b1cd1926758ab2dc69f9fbf896dab65e693a107fb48e9799" +
            "a0814d45f3ce051b5823aa9a4bee8677efab57ff145c9caa9d2160ea31bc0fb8"

    private val random = SecureRandom()

    fun encryptSm2Hex(plain: String, publicKeyHex: String = PLATFORM_SM2_PUBLIC_KEY): String =
        encryptSm2Hex(plain, publicKeyHex, random)

    /** [secureRandom] 只用于测试注入固定随机数以复现参考向量。 */
    internal fun encryptSm2Hex(plain: String, publicKeyHex: String, secureRandom: SecureRandom): String {
        val publicKey = decodePoint(publicKeyHex)
        val message = plain.toByteArray(Charsets.UTF_8)
        require(message.isNotEmpty()) { "SM2 明文不能为空" }

        var scalar: BigInteger
        do {
            scalar = BigInteger(N.bitLength(), secureRandom)
        } while (scalar.signum() == 0 || scalar.compareTo(N) >= 0)
        val c1 = multiply(scalar, G) ?: error("SM2 计算失败")
        val x2y2 = toFixed(multiply(scalar, publicKey) ?: error("SM2 计算失败"))

        // C3 = SM3(x2 || M || y2)；C2 = M ⊕ KDF(x2 || y2, 明文字节数)
        val c3 = sm3(x2y2.copyOfRange(0, 32) + message + x2y2.copyOfRange(32, 64))
        val keyStream = kdf(x2y2, message.size)
        val c2 = ByteArray(message.size) { (message[it].toInt() xor keyStream[it].toInt()).toByte() }
        return toHex(toFixed(c1) + c3 + c2)
    }

    // —— SM2 推荐曲线 sm2p256v1（GB/T 32918.5），仿射坐标，null 表示无穷远点 ——

    private val P = BigInteger("FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFF", 16)
    private val A = BigInteger("FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFC", 16)
    private val B = BigInteger("28E9FA9E9D9F5E344D5A9E4BCF6509A7F39789F515AB8F92DDBCBD414D940E93", 16)
    private val N = BigInteger("FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123", 16)
    private val G = Point(
        BigInteger("32C4AE2C1F1981195F9904466A39C9948FE30BBFF2660BE1715A4589334C74C7", 16),
        BigInteger("BC3736A2F4F6779C59BDCEE36B692153D0A9877CC62A474002DF32E52139F0A0", 16),
    )

    private class Point(val x: BigInteger, val y: BigInteger)

    private fun decodePoint(publicKeyHex: String): Point {
        val body = publicKeyHex.trim().removePrefix("04")
        require(body.length == 128 && body.all { it in '0'..'9' || it.lowercaseChar() in 'a'..'f' }) {
            "SM2 公钥须为 65 字节非压缩 hex"
        }
        val x = BigInteger(body.substring(0, 64), 16)
        val y = BigInteger(body.substring(64), 16)
        require(onCurve(x, y)) { "SM2 公钥不在 sm2p256v1 曲线上" }
        return Point(x, y)
    }

    private fun onCurve(x: BigInteger, y: BigInteger): Boolean =
        y.pow(2).subtract(x.pow(3).add(A.multiply(x)).add(B)).mod(P).signum() == 0

    private fun twice(p: Point): Point? {
        if (p.y.signum() == 0) return null
        // λ = (3x² + a) / 2y
        val lambda = p.x.pow(2).multiply(BigInteger.valueOf(3)).add(A)
            .multiply(p.y.shiftLeft(1).modInverse(P)).mod(P)
        val x3 = lambda.pow(2).subtract(p.x.shiftLeft(1)).mod(P)
        val y3 = lambda.multiply(p.x.subtract(x3)).subtract(p.y).mod(P)
        return Point(x3, y3)
    }

    private fun add(p: Point, q: Point?): Point? {
        if (q == null) return p
        if (p.x == q.x) {
            // 横坐标相同：重合点走倍点，相反点（q = -p）结果为无穷远点
            return if (p.y == q.y) twice(p) else null
        }
        val lambda = q.y.subtract(p.y).multiply(q.x.subtract(p.x).modInverse(P)).mod(P)
        val x3 = lambda.pow(2).subtract(p.x).subtract(q.x).mod(P)
        val y3 = lambda.multiply(p.x.subtract(x3)).subtract(p.y).mod(P)
        return Point(x3, y3)
    }

    private fun multiply(scalar: BigInteger, point: Point): Point? {
        var result: Point? = null
        for (bit in scalar.bitLength() - 1 downTo 0) {
            result = result?.let(::twice)
            if (scalar.testBit(bit)) result = result?.let { add(it, point) } ?: point
        }
        return result
    }

    // —— KDF（GB/T 32918.4）：SM3(z || ct)，ct 从 1 起按大端 32 位递增 ——

    private fun kdf(z: ByteArray, length: Int): ByteArray {
        val counter = ByteArray(4)
        return ByteArray(length).also { out ->
            var offset = 0
            var ct = 1
            while (offset < length) {
                for (i in 0 until 4) counter[i] = (ct ushr (24 - i * 8)).toByte()
                val block = sm3(z + counter)
                val size = minOf(block.size, length - offset)
                block.copyInto(out, offset, 0, size)
                offset += size
                ct++
            }
        }
    }

    // —— SM3 杂凑（GB/T 32905），输出 32 字节 ——

    private val IV = intArrayOf(
        0x7380166F, 0x4914B2B9, 0x172442D7, 0xDA8A0600.toInt(),
        0xA96F30BC.toInt(), 0x163138AA, 0xE38DEE4D.toInt(), 0xB0FB0E4E.toInt(),
    )
    private val T = IntArray(64) { if (it < 16) 0x79CC4519 else 0x7A879D8A.toInt() }

    internal fun sm3(message: ByteArray): ByteArray {
        // 补位：1 比特 1、若干 0、64 比特大端消息长度
        val bitLength = message.size * 8L
        val padded = ByteArray((message.size + 9 + 63) / 64 * 64)
        message.copyInto(padded)
        padded[message.size] = 0x80.toByte()
        for (i in 0 until 8) padded[padded.size - 1 - i] = (bitLength ushr (i * 8)).toByte()

        val w = IntArray(68)
        val v = IV.copyOf()
        for (block in padded.indices step 64) {
            for (j in 0 until 16) {
                val at = block + j * 4
                w[j] = ((padded[at].toInt() and 0xFF) shl 24) or ((padded[at + 1].toInt() and 0xFF) shl 16) or
                    ((padded[at + 2].toInt() and 0xFF) shl 8) or (padded[at + 3].toInt() and 0xFF)
            }
            for (j in 16 until 68) {
                w[j] = p1(w[j - 16] xor w[j - 9] xor w[j - 3].rotateLeft(15)) xor w[j - 13].rotateLeft(7) xor w[j - 6]
            }

            var a = v[0]
            var b = v[1]
            var c = v[2]
            var d = v[3]
            var e = v[4]
            var f = v[5]
            var g = v[6]
            var h = v[7]
            for (j in 0 until 64) {
                val ss1 = a.rotateLeft(12).plus(e).plus(T[j].rotateLeft(j % 32)).rotateLeft(7)
                val ss2 = ss1 xor a.rotateLeft(12)
                val tt1 = ((if (j < 16) a xor b xor c else (a and b) or (a and c) or (b and c)) + d + ss2 + (w[j] xor w[j + 4]))
                val tt2 = ((if (j < 16) e xor f xor g else (e and f) or (e.inv() and g)) + h + ss1 + w[j])
                d = c
                c = b.rotateLeft(9)
                b = a
                a = tt1
                h = g
                g = f.rotateLeft(19)
                f = e
                e = p0(tt2)
            }
            v[0] = v[0] xor a
            v[1] = v[1] xor b
            v[2] = v[2] xor c
            v[3] = v[3] xor d
            v[4] = v[4] xor e
            v[5] = v[5] xor f
            v[6] = v[6] xor g
            v[7] = v[7] xor h
        }
        return ByteArray(32).also { out ->
            for (i in 0 until 8) {
                out[i * 4] = (v[i] ushr 24).toByte()
                out[i * 4 + 1] = (v[i] ushr 16).toByte()
                out[i * 4 + 2] = (v[i] ushr 8).toByte()
                out[i * 4 + 3] = v[i].toByte()
            }
        }
    }

    private fun p0(x: Int): Int = x xor x.rotateLeft(9) xor x.rotateLeft(17)

    private fun p1(x: Int): Int = x xor x.rotateLeft(15) xor x.rotateLeft(23)

    // —— 编码 ——

    /** 坐标定长 32 字节：toByteArray() 可能带符号位或不足长，右对齐写入。 */
    private fun toFixed(point: Point): ByteArray = ByteArray(64).also {
        writeFixed(point.x, it, 0)
        writeFixed(point.y, it, 32)
    }

    private fun writeFixed(value: BigInteger, out: ByteArray, offset: Int) {
        val bytes = value.toByteArray()
        val start = maxOf(0, bytes.size - 32)
        bytes.copyInto(out, offset + 32 - (bytes.size - start), start)
    }

    internal fun toHex(bytes: ByteArray): String = buildString(bytes.size * 2) {
        for (byte in bytes) append(((byte.toInt() and 0xFF) + 0x100).toString(16).substring(1))
    }
}
