package com.suyuan.mobile
import org.junit.Assert.*
import org.junit.Test

class ReplyOutcomesTest {
    private fun file(id: String, name: String, group: String = "") = UploadedAttachment(id, name, "document", "application/octet-stream", "/$id", resourceRef = null, groupId = group)
    private fun chart(id: String, group: String) = file(id, "趋势.json", group).copy(visualId = "v1", renderer = "chart", resourceKey = "chart-spec", interactive = true, mimeType = "application/json")
    @Test fun placedChartHidesAllItsRenditions() {
        val chart = chart("c", "g")
        val image = file("i", "趋势.png", "g").copy(visualId = "v1", mimeType = "image/png")
        assertEquals(ReplyOutcomes(emptyList(), emptyList()), replyOutcomes(listOf(chart, image), setOf("c")))
    }
    @Test fun unplacedChartsCollapseAsOneOutcome() {
        val chart = chart("c", "g")
        val image = file("i", "趋势.png", "g").copy(mimeType = "image/png")
        val result = replyOutcomes(listOf(chart, image), emptySet())
        assertTrue(result.files.isEmpty())
        assertEquals(listOf("c"), result.others.map { it.fileId })
    }
    @Test fun reportFormatsMergeButUnrelatedFilesDoNot() {
        val result = replyOutcomes(listOf(file("a", "日报.docx", "report"), file("b", "日报.pdf", "report"), file("x", "数据.xlsx", "sheet")), emptySet())
        assertEquals(2, result.files.size)
        assertEquals("pdf", result.files[0].variants.single().format)
    }
    @Test fun hidesIntermediateResourcesWithoutHidingDeliverables() {
        val result = replyOutcomes(listOf(file("a", "配置.json"), file("b", "源.qmd"), file("c", "临时.csv").copy(resourceKind = "data"), file("d", "结果.xlsx")), emptySet())
        assertEquals(listOf("d"), result.files.map { it.fileId })
    }
    @Test fun staticImageIsFoldedAndVisibleWhenNotPlaced() {
        val result = replyOutcomes(listOf(file("a", "趋势.png").copy(mimeType = "image/png")), emptySet())
        assertEquals(1, result.others.size)
    }
}
