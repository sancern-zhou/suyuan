package com.suyuan.mobile

import org.junit.Assert.*
import org.junit.Test

class ChartReplyBlocksTest {
    private val firstId = "0123456789abcdef0123456789abcdef"
    private val secondId = "fedcba9876543210fedcba9876543210"

    private fun marker(id: String) = "[[chart:$id]]"
    private fun image(resourceId: String, fileId: String = "upload-$resourceId") = UploadedAttachment(
        fileId, "趋势.png", "image", "image/png", "/image/$resourceId", resourceRef = null,
        resourceId = resourceId, resourceKey = "primary:png", groupId = "chart-group",
    )
    private fun chart(resourceId: String) = UploadedAttachment(
        "spec-file", "趋势", "document", "application/json", "/chart/$resourceId", resourceRef = null,
        resourceId = resourceId, renderer = "chart", resourceKey = "chart-spec", interactive = true,
        groupId = "chart-group", previewUrl = "/image/$firstId",
    )

    @Test fun sameFilenameImagesStayBetweenTheirAnalysisParagraphs() {
        val blocks = chartReplyBlocks("开头\n${marker(firstId)}\n说明\n${marker(secondId)}\n结论", listOf(image(secondId), image(firstId)))
        assertEquals(5, blocks.size)
        assertEquals(firstId, (blocks[1] as ReplyBlock.Image).attachment.resourceId)
        assertEquals("\n说明\n", (blocks[2] as ReplyBlock.Text).content)
        assertEquals(secondId, (blocks[3] as ReplyBlock.Image).attachment.resourceId)
    }

    @Test fun groupMembersRenderAccordingToTheReferencedResourceId() {
        val image = image(firstId)
        val chart = chart(secondId)
        for (order in listOf(listOf(image, chart), listOf(chart, image))) {
            val blocks = chartReplyBlocks("${marker(firstId)}\n${marker(secondId)}", order)
            assertEquals(ReplyBlock.Image(image), blocks[0])
            assertEquals(ReplyBlock.Chart(chart), blocks[2])
        }
        assertEquals(listOf(ReplyBlock.Chart(chart)), chartReplyBlocks(marker(secondId), listOf(chart)))
    }

    @Test fun validReferencesRequireAnExactResourceId() {
        val fileIdOnly = image("", fileId = firstId)
        assertEquals(listOf(ReplyBlock.Text("【图表不可用】")), chartReplyBlocks(marker(firstId), listOf(fileIdOnly)))
        for (id in listOf("chart_0", "run/my chart.png", firstId.uppercase(), firstId + "a")) {
            assertEquals(listOf(ReplyBlock.Text(marker(id))), chartReplyBlocks(marker(id), listOf(image(id))))
        }
    }

    @Test fun codeExamplesAndEscapesAreNotRenderedAsCharts() {
        val literal = "示例 `${marker(firstId)}`\n\n```text\n${marker(firstId)}\n```\n\n    ${marker(firstId)}\n\\${marker(firstId)}\n"
        assertEquals(
            listOf(ReplyBlock.Text(literal), ReplyBlock.Image(image(firstId))),
            chartReplyBlocks(literal + marker(firstId), listOf(image(firstId))),
        )
    }
}
