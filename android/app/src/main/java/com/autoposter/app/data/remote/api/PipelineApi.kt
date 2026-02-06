package com.autoposter.app.data.remote.api

import com.autoposter.app.data.remote.dto.*
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path

interface PipelineApi {

    @POST("/api/pipeline/start")
    suspend fun startPipeline(@Body request: PipelineStartRequest): PipelineStartResponse

    @GET("/api/pipeline/status/{pipelineId}")
    suspend fun getPipelineStatus(@Path("pipelineId") pipelineId: String): PipelineStatusResponse

    @GET("/api/pipeline/list")
    suspend fun listPipelines(): PipelineListResponse

    @POST("/api/pipeline/cancel/{pipelineId}")
    suspend fun cancelPipeline(@Path("pipelineId") pipelineId: String): PipelineCancelResponse
}
