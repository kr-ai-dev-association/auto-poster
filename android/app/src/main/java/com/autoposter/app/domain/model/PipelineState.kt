package com.autoposter.app.domain.model

enum class PipelineStepId(val id: String, val label: String) {
    PLAN("plan_generation", "기획"),
    IMAGES("image_generation", "이미지"),
    PDF("pdf_generation", "PDF"),
    SCRIPT("script_generation", "대본"),
    AUDIO("audio_generation", "오디오"),
    VIDEO("video_generation", "비디오"),
    YOUTUBE("youtube_upload", "YouTube");
}

data class PipelineUiState(
    val isRunning: Boolean = false,
    val pipelineId: String? = null,
    val status: String = "",
    val progress: Int = 0,
    val message: String = "",
    val currentStep: String = "",
    val completedSteps: List<String> = emptyList(),
    val result: PipelineResultUi? = null,
    val error: String? = null
)

data class PipelineResultUi(
    val title: String?,
    val youtubeUrl: String?,
    val duration: String?
)

data class PipelineHistoryItem(
    val id: String,
    val topic: String?,
    val status: String,
    val title: String?,
    val youtubeUrl: String?
)
