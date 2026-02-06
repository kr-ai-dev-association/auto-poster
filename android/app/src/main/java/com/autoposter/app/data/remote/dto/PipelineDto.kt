package com.autoposter.app.data.remote.dto

import com.google.gson.annotations.SerializedName

data class PipelineStartRequest(
    val topic: String,
    val category: String = "tech",
    @SerializedName("target_slides") val targetSlides: Int = 15,
    val language: String = "ko",
    @SerializedName("additional_instructions") val additionalInstructions: String = "",
    val voice: String = "Leda",
    @SerializedName("script_style") val scriptStyle: String = "educational",
    @SerializedName("youtube_privacy") val youtubePrivacy: String = "private"
)

data class PipelineStartResponse(
    val status: String,
    @SerializedName("pipeline_id") val pipelineId: String,
    val message: String
)

data class PipelineStatusResponse(
    val status: String,
    val pipeline: PipelineData?
)

data class PipelineData(
    val id: String,
    @SerializedName("content_id") val contentId: String?,
    val topic: String?,
    val category: String?,
    val language: String?,
    val status: String,
    @SerializedName("current_step") val currentStep: String?,
    val progress: Int,
    @SerializedName("steps_completed") val stepsCompleted: List<String>,
    val error: String?,
    val message: String?,
    val result: PipelineResult?,
    @SerializedName("started_at") val startedAt: String?,
    @SerializedName("completed_at") val completedAt: String?,
    val duration: String?,
    @SerializedName("user_id") val userId: Int?
)

data class PipelineResult(
    @SerializedName("plan_id") val planId: String?,
    val title: String?,
    val youtube: YouTubeResult?
)

data class YouTubeResult(
    @SerializedName("video_id") val videoId: String?,
    val url: String?,
    val error: String?
)

data class PipelineListResponse(
    val status: String,
    val pipelines: List<PipelineData>
)

data class PipelineCancelResponse(
    val status: String,
    val message: String
)
