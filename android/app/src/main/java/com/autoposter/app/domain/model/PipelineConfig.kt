package com.autoposter.app.domain.model

data class PipelineConfig(
    val topic: String,
    val category: String = "tech",
    val targetSlides: Int = 15,
    val language: String = "ko",
    val additionalInstructions: String = "",
    val voice: String = "Leda",
    val youtubePrivacy: String = "private"
)

data class Category(
    val id: String,
    val nameKo: String,
    val nameEn: String?
)

data class Language(
    val id: String,
    val nameKo: String,
    val nameEn: String
)

object LanguageData {
    val languages = listOf(
        Language("ko", "한국어", "Korean"),
        Language("en", "영어", "English"),
    )
}
