package com.suyuan.mobile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.math.BigInteger
import java.security.SecureRandom

/**
 * 公司平台 SM2 加密的已知答案与线上格式测试。
 *
 * 参考向量由独立实现生成，backend/tests/social/test_company_password_auth.py 用同批密文反向解密：
 * SM3 取 sm-crypto 与 gmssl 两个实现一致的输出；SM2 取 gmssl 固定随机数 k 的输出，
 * 其中标准例与 GB/T 32918.5 附录 A.2 的公布值一致（C1 横坐标尾位按曲线方程复算为 3）。
 */
class CompanyCryptoTest {

    private val fixedK = "59276e27d506861a16680f3ad9c02dccef3cc1fa3cdbe4ce6d54b80deac1bc21"

    // 非平台真实密钥：node sm-crypto generateKeyPairHex 生成的测试密钥对
    private val testPublicKey =
        "040a59760d53fefaea09b0e3668c0b0e99b7901a79ea618264fb3a6562d0ea685ce" +
            "25a7557c340af784daee365b446f680c6375878ebe87b14c5f5c6d2dfc7b03c"
    private val standardPublicKey =
        "0409f9df311e5421a150dd7d161e4bc5c672179fad1833fc076bb08ff356f35020" +
            "ccea490ce26775a52dc6ea718cc1aa600aed05fbf35e084a6632f6072da9ad13"

    @Test
    fun sm3MatchesReferenceVectors() {
        // 覆盖补位边界：55/56 字节（一组内两种补位）、64 字节、65/119 字节（跨组）
        assertSm3(ByteArray(0), "1ab21d8355cfa17f8e61194831e81a8f22bec8c728fefb747ed035eb5082aa2b")
        assertSm3("abc".toByteArray(), "66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0")
        assertSm3(ByteArray(55) { it.toByte() }, "a79cf9dcee3404abf7f769698201647fd9d3ff61d629d0f58bb4b5579a427db8")
        assertSm3(ByteArray(56) { it.toByte() }, "62f7363b15f4de76dd925c493b9d6d00d4ba0ef2a1f334c1d0f13b293aeb40d1")
        assertSm3(ByteArray(64) { it.toByte() }, "93566f236d157aae078d1ddb5cebdbba1520b5142e22a8915564345ba2ae1d63")
        assertSm3(ByteArray(65) { ((it * 7 + 3) and 0xFF).toByte() }, "dc068b29e9179526942e7392faf7900e793123407a0e60a104ef6443c254f20b")
        assertSm3(ByteArray(119) { ((it * 7 + 3) and 0xFF).toByte() }, "3b1ba88b91c3a5e9d38e93afd6986c0f3389889bdde9635230dae0ae10fd5270")
        assertSm3("张三|密码|公司账号".toByteArray(), "8116ead089bbaadd253a15125d52b21e223feeeb246802d36b829018ad7ecf96")
    }

    @Test
    fun matchesStandardEncryptionExample() {
        // GB/T 32918.5 附录 A.2 例：标准公钥、固定 k、明文 "encryption standard"
        assertEquals(
            "04ebfc718e8d1798620432268e77feb6415e2ede0e073c0f4f640ecd2e149a73" +
                "e858f9d81e5430a57b36daab8f950a3c64e6ee6a63094d99283aff767e124df0" +
                "59983c18f809e262923c53aec295d30383b54e39d609d160afcb1908d0bd8766" +
                "21886ca989ca9c7d58087307ca93092d651efa",
            CompanyCrypto.encryptSm2Hex("encryption standard", standardPublicKey, fixedRandom(fixedK)),
        )
    }

    @Test
    fun matchesGmsslReferenceVectors() {
        val vectors = listOf(
            "zhangsan" to (
                "04ebfc718e8d1798620432268e77feb6415e2ede0e073c0f4f640ecd2e149a73" +
                    "e858f9d81e5430a57b36daab8f950a3c64e6ee6a63094d99283aff767e124df0" +
                    "a8dd23a96ccde66fc09ba9fad03a6a75b9c0dcece8451de30a419b996a4c48e537" +
                    "57951066e7eaea"
            ),
            // 中文多字节
            "张三|密码|公司账号" to (
                "04ebfc718e8d1798620432268e77feb6415e2ede0e073c0f4f640ecd2e149a73" +
                    "e858f9d81e5430a57b36daab8f950a3c64e6ee6a63094d99283aff767e124df0" +
                    "d31f757f344c616daeb1e8a4e7866953d03a2302b83dfd8c7a385d4f347f92ef" +
                    "a883549ab91df761ed7c7f3ae5ca4b3d1f6980031afcf56e20fb"
            ),
            // 46 字节：KDF 跨两个 SM3 块
            "Tr0ub4dor&3-quis-custodiet-ipsos-custodes-2026" to (
                "04ebfc718e8d1798620432268e77feb6415e2ede0e073c0f4f640ecd2e149a73" +
                    "e858f9d81e5430a57b36daab8f950a3c64e6ee6a63094d99283aff767e124df0" +
                    "8afa148156618868830f5180cc99301c54fc90aecc7f5d213f7565136d6d81a8" +
                    "194dc40b63a0efeb30dcabb715c3c7cb9eef7ac8862737e2ca38d3bbac71c427" +
                    "4770f5ec922e66a7e50ed447897e"
            ),
        )
        for ((plain, cipher) in vectors) {
            assertEquals(cipher, CompanyCrypto.encryptSm2Hex(plain, testPublicKey, fixedRandom(fixedK)))
        }
    }

    @Test
    fun wireFormatMatchesWebSmCrypto() {
        val plain = "zhangsan|密码|公司账号"
        val first = CompanyCrypto.encryptSm2Hex(plain)
        val second = CompanyCrypto.encryptSm2Hex(plain)
        // C1(64B，无 04 前缀) + C3(32B) + C2(与明文等长)，小写 hex；随机数 k 每次不同
        val expectedLength = 128 + 64 + 2 * plain.toByteArray().size
        for (cipher in listOf(first, second)) {
            assertEquals(expectedLength, cipher.length)
            assertTrue(cipher.all { it in '0'..'9' || it in 'a'..'f' })
        }
        assertNotEquals(first, second)
    }

    @Test
    fun platformPublicKeyIsUsable() {
        assertEquals(128 + 64 + 2 * 5, CompanyCrypto.encryptSm2Hex("probe").length)
    }

    @Test
    fun rejectsMalformedKeyAndEmptyPlain() {
        val malformedKeys = listOf(
            "",
            "0412345",
            "04" + "zz".repeat(64),
            "04" + "00".repeat(64),
            "04" + "11".repeat(64),
        )
        for (key in malformedKeys) {
            try {
                CompanyCrypto.encryptSm2Hex("probe", key, fixedRandom(fixedK))
                fail("should reject key $key")
            } catch (expected: IllegalArgumentException) {
                // 非法公钥必须拒绝，不得回退到别的密钥
            }
        }
        try {
            CompanyCrypto.encryptSm2Hex("", testPublicKey, fixedRandom(fixedK))
            fail("should reject empty plaintext")
        } catch (expected: IllegalArgumentException) {
            // 空明文拒绝
        }
    }

    private fun assertSm3(message: ByteArray, expected: String) {
        assertEquals(expected, CompanyCrypto.toHex(CompanyCrypto.sm3(message)))
    }

    /** 每次构造 BigInteger(256, random) 读取 32 字节，按给定顺序返回固定随机数。 */
    private fun fixedRandom(vararg scalars: String) = object : SecureRandom() {
        private var index = 0

        override fun nextBytes(bytes: ByteArray) {
            val source = BigInteger(scalars[index], 16).toByteArray()
            index++
            source.copyInto(bytes, bytes.size - source.size)
        }
    }
}
