package com.autoposter.app.data.repository

import com.autoposter.app.data.local.TokenManager
import com.autoposter.app.data.remote.api.PipelineApi
import com.autoposter.app.data.remote.dto.*
import com.autoposter.app.domain.model.PipelineConfig
import retrofit2.HttpException
import javax.inject.Inject

class PipelineRepository @Inject constructor(
    private val pipelineApi: PipelineApi,
    private val tokenManager: TokenManager
) {
    suspend fun startPipeline(config: PipelineConfig): Result<String> {
        return try {
            val request = PipelineStartRequest(
                topic = config.topic,
                category = config.category,
                targetSlides = config.targetSlides,
                language = config.language,
                additionalInstructions = config.additionalInstructions,
                voice = config.voice,
                youtubePrivacy = config.youtubePrivacy
            )
            val response = pipelineApi.startPipeline(request)
            if (response.status == "started") {
                tokenManager.savePipelineId(response.pipelineId)
                Result.success(response.pipelineId)
            } else {
                Result.failure(Exception(response.message))
            }
        } catch (e: HttpException) {
            Result.failure(Exception("파이프라인 시작 실패 (${e.code()})"))
        } catch (e: Exception) {
            Result.failure(Exception("서버에 연결할 수 없습니다."))
        }
    }

    suspend fun getPipelineStatus(pipelineId: String): Result<PipelineData> {
        return try {
            val response = pipelineApi.getPipelineStatus(pipelineId)
            if (response.pipeline != null) {
                Result.success(response.pipeline)
            } else {
                Result.failure(Exception("파이프라인을 찾을 수 없습니다."))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun cancelPipeline(pipelineId: String): Result<Unit> {
        return try {
            pipelineApi.cancelPipeline(pipelineId)
            Result.success(Unit)
        } catch (e: HttpException) {
            Result.failure(Exception("파이프라인을 취소할 수 없습니다."))
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun listPipelines(): Result<List<PipelineData>> {
        return try {
            val response = pipelineApi.listPipelines()
            Result.success(response.pipelines)
        } catch (e: Exception) {
            Result.success(emptyList())
        }
    }

    suspend fun getSavedPipelineId(): String? = tokenManager.getPipelineId()

    suspend fun clearSavedPipelineId() = tokenManager.clearPipelineId()
}
