package com.suyuan.mobile

import org.junit.Assert.*
import org.junit.Test

class ChartReplyBlocksTest {
    private fun image(id: String, visual: String) = UploadedAttachment(id, "趋势.png", "image", "image/png", "/image/$id", resourceRef = null, visualId = visual, resourceKey = "chart-image")
    private fun chart(id: String, visual: String) = UploadedAttachment(id, "趋势", "document", "application/json", "/chart/$id", resourceRef = null, visualId = visual, renderer = "chart", resourceKey = "chart-spec", interactive = true)

    @Test fun staticChartsStayBetweenTheirAnalysisParagraphs() {
        val blocks = chartReplyBlocks("开头\n[[chart:matplotlib_123]]\n说明\n[[chart:matplotlib_456]]\n结论", listOf(image("r1", "matplotlib_123"), image("r2", "matplotlib_456")))
        assertEquals(5, blocks.size)
        assertEquals("r1", (blocks[1] as ReplyBlock.Image).attachment.fileId)
        assertEquals("\n说明\n", (blocks[2] as ReplyBlock.Text).content)
        assertEquals("r2", (blocks[3] as ReplyBlock.Image).attachment.fileId)
    }

    @Test fun mixedReplyPreservesBothImageAndInteractiveChart() {
        val blocks = chartReplyBlocks("[[chart:v1]]\n[[chart:v2]]", listOf(image("r1", "v1"), chart("r2", "v2")))
        assertTrue(blocks[0] is ReplyBlock.Image)
        assertTrue(blocks[2] is ReplyBlock.Chart)
    }

    @Test fun interactiveChartWinsOverItsStaticRenditionRegardlessOfOrder() {
        val resources = listOf(chart("r1", "v1"), image("r2", "v1"))
        for (order in listOf(resources, resources.reversed())) {
            assertEquals("r1", (chartReplyBlocks("[[chart:v1]]", order)[0] as ReplyBlock.Chart).attachment.fileId)
        }
    }

    @Test fun missingResourcesKeepReferencesUntilTheyArrive() {
        assertEquals(listOf(ReplyBlock.Text("[[chart:missing]]")), chartReplyBlocks("[[chart:missing]]", emptyList()))
        assertTrue(chartReplyBlocks("[[chart:r1]]", listOf(image("r1", "v1")))[0] is ReplyBlock.Image)
    }
}
